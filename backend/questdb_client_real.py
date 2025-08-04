# backend/questdb_client_real.py
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import pool
import numpy as np
from datetime import datetime, timedelta
import struct
import socket
import logging
from typing import List, Dict, Optional, Tuple, Generator
import time
from contextlib import contextmanager
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
import queue
import threading

logger = logging.getLogger(__name__)

@dataclass
class TimeSeriesPoint:
    timestamp: datetime
    amplitude: int
    sensor_id: str
    metadata: Optional[Dict] = None

class QuestDBClient:
    """Production QuestDB client with connection pooling and streaming."""
    
    def __init__(self, host: str = "localhost", pg_port: int = 8812, 
                 ilp_port: int = 9009, user: str = "admin", 
                 password: str = "quest", database: str = "qdb",
                 min_connections: int = 2, max_connections: int = 10):
        
        self.host = host
        self.pg_port = pg_port
        self.ilp_port = ilp_port
        self.user = user
        self.password = password
        self.database = database
        
        # Initialize connection pool
        self.connection_pool = psycopg2.pool.ThreadedConnectionPool(
            min_connections,
            max_connections,
            host=host,
            port=pg_port,
            user=user,
            password=password,
            database=database
        )
        
        # ILP sender configuration
        self.ilp_buffer_size = 65536  # 64KB buffer
        self.ilp_send_interval = 0.1  # Send every 100ms
        self._ilp_socket = None
        self._ilp_buffer = []
        self._ilp_lock = threading.Lock()
        self._start_ilp_sender()
        
    @contextmanager
    def get_connection(self):
        """Get connection from pool with automatic return."""
        conn = self.connection_pool.getconn()
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise
        finally:
            self.connection_pool.putconn(conn)
    
    def _start_ilp_sender(self):
        """Start background thread for ILP batch sending."""
        def sender_loop():
            while True:
                try:
                    self._flush_ilp_buffer()
                    time.sleep(self.ilp_send_interval)
                except Exception as e:
                    logger.error(f"ILP sender error: {str(e)}")
                    
        sender_thread = threading.Thread(target=sender_loop, daemon=True)
        sender_thread.start()
    
    def _get_ilp_socket(self):
        """Get or create ILP socket connection."""
        if self._ilp_socket is None:
            self._ilp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._ilp_socket.connect((self.host, self.ilp_port))
        return self._ilp_socket
    
    def _flush_ilp_buffer(self):
        """Flush ILP buffer to QuestDB."""
        with self._ilp_lock:
            if not self._ilp_buffer:
                return
                
            buffer_copy = self._ilp_buffer.copy()
            self._ilp_buffer.clear()
        
        try:
            sock = self._get_ilp_socket()
            message = '\n'.join(buffer_copy) + '\n'
            sock.sendall(message.encode('utf-8'))
        except Exception as e:
            logger.error(f"Failed to send ILP data: {str(e)}")
            # Recreate socket on error
            if self._ilp_socket:
                self._ilp_socket.close()
                self._ilp_socket = None
            raise
    
    def create_table(self, table_name: str, schema: Dict[str, str], 
                    timestamp_column: str = "ts", partition_by: str = "HOUR"):
        """Create a time-series table with specified schema."""
        columns = []
        for col_name, col_type in schema.items():
            columns.append(f"{col_name} {col_type}")
        
        columns_str = ", ".join(columns)
        
        query = f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            {columns_str}
        ) timestamp({timestamp_column}) PARTITION BY {partition_by}
        """
        
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query)
                
        logger.info(f"Created table {table_name}")
    
    def ingest_audio_samples(self, table_name: str, samples: np.ndarray,
                           start_timestamp: datetime, sample_rate: int,
                           sensor_id: str, file_name: Optional[str] = None,
                           batch_size: int = 100000) -> int:
        """Ingest audio samples into QuestDB using ILP."""
        total_samples = len(samples)
        ns_per_sample = int(1e9 / sample_rate)
        start_ns = int(start_timestamp.timestamp() * 1e9)
        
        ingested = 0
        
        for i in range(0, total_samples, batch_size):
            batch_end = min(i + batch_size, total_samples)
            batch_samples = samples[i:batch_end]
            
            with self._ilp_lock:
                for j, sample in enumerate(batch_samples):
                    timestamp_ns = start_ns + (i + j) * ns_per_sample
                    
                    # Build ILP line
                    line_parts = [table_name]
                    
                    # Tags
                    tags = [f"sensor={sensor_id}"]
                    if file_name:
                        tags.append(f"file={file_name}")
                    line_parts.append(','.join(tags))
                    
                    # Fields
                    line_parts.append(f"amplitude={int(sample)}i")
                    
                    # Timestamp
                    line_parts.append(str(timestamp_ns))
                    
                    # Add to buffer
                    self._ilp_buffer.append(' '.join(line_parts))
                    
                    # Flush if buffer is full
                    if len(self._ilp_buffer) >= 10000:
                        self._flush_ilp_buffer()
                        
            ingested += len(batch_samples)
            
        # Final flush
        self._flush_ilp_buffer()
        
        logger.info(f"Ingested {ingested} samples into {table_name}")
        return ingested
    
    def query_time_range(self, table_name: str, start_time: datetime,
                        end_time: datetime, columns: List[str] = None,
                        where_clause: Optional[str] = None,
                        order_by: str = "ts ASC",
                        limit: Optional[int] = None) -> List[Dict]:
        """Query data within a time range."""
        if columns:
            columns_str = ", ".join(columns)
        else:
            columns_str = "*"
            
        query = f"""
        SELECT {columns_str}
        FROM {table_name}
        WHERE ts >= '{start_time.isoformat()}' 
          AND ts < '{end_time.isoformat()}'
        """
        
        if where_clause:
            query += f" AND {where_clause}"
            
        if order_by:
            query += f" ORDER BY {order_by}"
            
        if limit:
            query += f" LIMIT {limit}"
            
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query)
                return cursor.fetchall()
    
    def stream_audio_data(self, table_name: str, sensor_id: str,
                         start_time: datetime, end_time: datetime,
                         chunk_size: int = 1000000) -> Generator[np.ndarray, None, None]:
        """Stream audio data in chunks to handle large queries."""
        query = f"""
        SELECT amplitude, ts
        FROM {table_name}
        WHERE sensor = '{sensor_id}'
          AND ts >= '{start_time.isoformat()}'
          AND ts < '{end_time.isoformat()}'
        ORDER BY ts
        """
        
        with self.get_connection() as conn:
            with conn.cursor('audio_stream_cursor') as cursor:
                cursor.itersize = chunk_size
                cursor.execute(query)
                
                chunk = []
                for row in cursor:
                    chunk.append(row[0])  # amplitude
                    
                    if len(chunk) >= chunk_size:
                        yield np.array(chunk, dtype=np.int16)
                        chunk = []
                
                # Yield remaining data
                if chunk:
                    yield np.array(chunk, dtype=np.int16)
    
    def get_audio_statistics(self, table_name: str, sensor_id: str,
                           start_time: datetime, end_time: datetime,
                           window_ms: int = 100) -> List[Dict]:
        """Get windowed statistics for visualization."""
        query = f"""
        SELECT 
            ts,
            min(amplitude) as min_amplitude,
            max(amplitude) as max_amplitude,
            avg(amplitude) as avg_amplitude,
            stddev(amplitude) as std_amplitude,
            count(*) as sample_count
        FROM {table_name}
        WHERE sensor = '{sensor_id}'
          AND ts >= '{start_time.isoformat()}'
          AND ts < '{end_time.isoformat()}'
        SAMPLE BY {window_ms}ms
        FILL(NULL)
        """
        
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query)
                return cursor.fetchall()
    
    def parallel_ingest(self, table_name: str, file_paths: List[str],
                       sensor_id: str, num_workers: int = 4) -> Dict[str, Any]:
        """Ingest multiple audio files in parallel."""
        from backend.audio_processor import AudioProcessor
        processor = AudioProcessor()
        
        results = {
            'successful': 0,
            'failed': 0,
            'total_samples': 0,
            'errors': []
        }
        
        def ingest_file(file_path: str) -> Tuple[bool, int, Optional[str]]:
            try:
                # Load audio file
                audio, sr = processor.load_audio_file(file_path)
                
                # Extract timestamp from filename
                from pathlib import Path
                filename = Path(file_path).stem
                # Assuming format: SENSOR_YYYYMMDD_HHMMSS
                parts = filename.split('_')
                if len(parts) >= 3:
                    date_str = parts[-2]
                    time_str = parts[-1]
                    timestamp = datetime.strptime(f"{date_str}_{time_str}", 
                                                "%Y%m%d_%H%M%S")
                else:
                    timestamp = datetime.now()
                
                # Resample if needed
                if sr != 48000:
                    audio = processor.resample_audio(audio, sr, 48000)
                    sr = 48000
                
                # Ingest samples
                count = self.ingest_audio_samples(
                    table_name, audio, timestamp, sr, 
                    sensor_id, Path(file_path).name
                )
                
                return True, count, None
                
            except Exception as e:
                return False, 0, str(e)
        
        # Process files in parallel
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            future_to_file = {
                executor.submit(ingest_file, fp): fp 
                for fp in file_paths
            }
            
            for future in as_completed(future_to_file):
                file_path = future_to_file[future]
                success, sample_count, error = future.result()
                
                if success:
                    results['successful'] += 1
                    results['total_samples'] += sample_count
                    logger.info(f"Ingested {file_path}: {sample_count} samples")
                else:
                    results['failed'] += 1
                    results['errors'].append({
                        'file': file_path,
                        'error': error
                    })
                    logger.error(f"Failed to ingest {file_path}: {error}")
        
        return results
    
    def check_data_availability(self, table_name: str, sensor_id: str,
                              start_time: datetime, end_time: datetime) -> bool:
        """Check if data exists for the specified time range."""
        query = f"""
        SELECT COUNT(*) as count
        FROM {table_name}
        WHERE sensor = '{sensor_id}'
          AND ts >= '{start_time.isoformat()}'
          AND ts < '{end_time.isoformat()}'
        LIMIT 1
        """
        
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query)
                    result = cursor.fetchone()
                    return result[0] > 0 if result else False
        except Exception as e:
            logger.error(f"Error checking data availability: {str(e)}")
            return False
    
    def get_sensor_time_bounds(self, table_name: str, 
                             sensor_id: str) -> Optional[Tuple[datetime, datetime]]:
        """Get the earliest and latest timestamps for a sensor."""
        query = f"""
        SELECT 
            min(ts) as min_ts,
            max(ts) as max_ts
        FROM {table_name}
        WHERE sensor = '{sensor_id}'
        """
        
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query)
                result = cursor.fetchone()
                
                if result and result[0] and result[1]:
                    return (result[0], result[1])
                return None
    
    def cleanup_old_data(self, table_name: str, days_to_keep: int = 30) -> int:
        """Delete data older than specified days."""
        cutoff_date = datetime.now() - timedelta(days=days_to_keep)
        
        query = f"""
        DELETE FROM {table_name}
        WHERE ts < '{cutoff_date.isoformat()}'
        """
        
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query)
                deleted = cursor.rowcount
                
        logger.info(f"Deleted {deleted} rows older than {days_to_keep} days from {table_name}")
        return deleted
    
    def close(self):
        """Clean up resources."""
        if self._ilp_socket:
            self._ilp_socket.close()
        self.connection_pool.closeall()