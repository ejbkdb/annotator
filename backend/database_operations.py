# backend/database_operations.py
import sqlite3
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any, Tuple
import time
import json
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class AnnotationStatus(Enum):
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"
    PROCESSING = "processing"

@dataclass
class AnnotationRecord:
    id: str
    sensor_id: str
    start_timestamp: datetime
    end_timestamp: datetime
    vehicle_type: str
    action: str
    location: str
    confidence: float
    metadata: Dict[str, Any]
    status: AnnotationStatus
    created_at: datetime
    updated_at: datetime

class DatabaseOperations:
    """Production database operations with real SQL queries and error handling."""
    
    def __init__(self, db_url: str, max_retries: int = 3, retry_delay: float = 1.0):
        self.db_url = db_url
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.is_postgres = db_url.startswith('postgresql://')
        
    @contextmanager
    def get_connection(self):
        """Get database connection with automatic cleanup."""
        conn = None
        try:
            if self.is_postgres:
                conn = psycopg2.connect(self.db_url)
                conn.autocommit = False
            else:
                conn = sqlite3.connect(self.db_url)
                conn.row_factory = sqlite3.Row
            yield conn
            conn.commit()
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Database error: {str(e)}")
            raise
        finally:
            if conn:
                conn.close()
    
    def execute_with_retry(self, query: str, params: tuple = (), 
                          fetch: str = None) -> Any:
        """Execute query with automatic retry on failure."""
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                with self.get_connection() as conn:
                    if self.is_postgres:
                        cursor = conn.cursor(cursor_factory=RealDictCursor)
                    else:
                        cursor = conn.cursor()
                    
                    cursor.execute(query, params)
                    
                    if fetch == 'one':
                        result = cursor.fetchone()
                        return dict(result) if result else None
                    elif fetch == 'all':
                        results = cursor.fetchall()
                        return [dict(row) for row in results]
                    else:
                        return cursor.rowcount
                        
            except (sqlite3.OperationalError, psycopg2.OperationalError) as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay * (attempt + 1))
                    logger.warning(f"Database query failed, retrying ({attempt + 1}/{self.max_retries})")
                continue
            except Exception as e:
                logger.error(f"Query failed: {query[:100]}... Error: {str(e)}")
                raise
                
        raise last_error
    
    def get_annotations_for_window(self, sensor_id: str, start_time: datetime, 
                                 end_time: datetime) -> List[Dict[str, Any]]:
        """Get all annotations that overlap with the specified time window."""
        query = """
        SELECT 
            a.id,
            a.sensor_id,
            a.start_timestamp,
            a.end_timestamp,
            a.vehicle_type,
            a.action,
            a.location,
            a.confidence,
            a.metadata,
            a.status,
            a.created_at,
            a.updated_at,
            v.category as vehicle_category,
            v.subclass as vehicle_subclass
        FROM annotations a
        LEFT JOIN vehicle_types v ON a.vehicle_type = v.type_id
        WHERE a.sensor_id = %s
            AND a.start_timestamp < %s
            AND a.end_timestamp > %s
            AND a.status != %s
        ORDER BY a.start_timestamp
        """
        
        if not self.is_postgres:
            query = query.replace('%s', '?')
        
        params = (sensor_id, end_time, start_time, AnnotationStatus.REJECTED.value)
        results = self.execute_with_retry(query, params, fetch='all')
        
        # Parse JSON metadata field
        for result in results:
            if isinstance(result.get('metadata'), str):
                try:
                    result['metadata'] = json.loads(result['metadata'])
                except json.JSONDecodeError:
                    result['metadata'] = {}
                    
        return results
    
    def insert_annotation(self, annotation: AnnotationRecord) -> str:
        """Insert new annotation record with proper transaction handling."""
        query = """
        INSERT INTO annotations (
            id, sensor_id, start_timestamp, end_timestamp,
            vehicle_type, action, location, confidence,
            metadata, status, created_at, updated_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        
        if not self.is_postgres:
            query = query.replace('%s', '?')
        
        metadata_json = json.dumps(annotation.metadata)
        params = (
            annotation.id,
            annotation.sensor_id,
            annotation.start_timestamp,
            annotation.end_timestamp,
            annotation.vehicle_type,
            annotation.action,
            annotation.location,
            annotation.confidence,
            metadata_json,
            annotation.status.value,
            annotation.created_at,
            annotation.updated_at
        )
        
        self.execute_with_retry(query, params)
        logger.info(f"Inserted annotation {annotation.id} for sensor {annotation.sensor_id}")
        return annotation.id
    
    def update_annotation_status(self, annotation_id: str, 
                               new_status: AnnotationStatus,
                               metadata_update: Optional[Dict] = None) -> bool:
        """Update annotation status with optional metadata update."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            if metadata_update:
                # Fetch current metadata
                select_query = "SELECT metadata FROM annotations WHERE id = %s"
                if not self.is_postgres:
                    select_query = select_query.replace('%s', '?')
                    
                cursor.execute(select_query, (annotation_id,))
                result = cursor.fetchone()
                
                if result:
                    current_metadata = json.loads(result[0] if result[0] else '{}')
                    current_metadata.update(metadata_update)
                    metadata_json = json.dumps(current_metadata)
                    
                    update_query = """
                    UPDATE annotations 
                    SET status = %s, metadata = %s, updated_at = %s
                    WHERE id = %s
                    """
                    params = (new_status.value, metadata_json, datetime.utcnow(), annotation_id)
                else:
                    return False
            else:
                update_query = """
                UPDATE annotations 
                SET status = %s, updated_at = %s
                WHERE id = %s
                """
                params = (new_status.value, datetime.utcnow(), annotation_id)
            
            if not self.is_postgres:
                update_query = update_query.replace('%s', '?')
                
            cursor.execute(update_query, params)
            return cursor.rowcount > 0
    
    def get_annotations_by_criteria(self, sensor_ids: Optional[List[str]] = None,
                                  vehicle_types: Optional[List[str]] = None,
                                  actions: Optional[List[str]] = None,
                                  start_date: Optional[datetime] = None,
                                  end_date: Optional[datetime] = None,
                                  status: Optional[AnnotationStatus] = None,
                                  limit: int = 1000) -> List[Dict[str, Any]]:
        """Query annotations with multiple filter criteria."""
        query_parts = ["SELECT * FROM annotations WHERE 1=1"]
        params = []
        
        if sensor_ids:
            placeholders = ','.join(['%s'] * len(sensor_ids))
            query_parts.append(f"AND sensor_id IN ({placeholders})")
            params.extend(sensor_ids)
            
        if vehicle_types:
            placeholders = ','.join(['%s'] * len(vehicle_types))
            query_parts.append(f"AND vehicle_type IN ({placeholders})")
            params.extend(vehicle_types)
            
        if actions:
            placeholders = ','.join(['%s'] * len(actions))
            query_parts.append(f"AND action IN ({placeholders})")
            params.extend(actions)
            
        if start_date:
            query_parts.append("AND start_timestamp >= %s")
            params.append(start_date)
            
        if end_date:
            query_parts.append("AND end_timestamp <= %s")
            params.append(end_date)
            
        if status:
            query_parts.append("AND status = %s")
            params.append(status.value)
            
        query_parts.append("ORDER BY start_timestamp DESC")
        query_parts.append(f"LIMIT {limit}")
        
        query = ' '.join(query_parts)
        if not self.is_postgres:
            query = query.replace('%s', '?')
            
        return self.execute_with_retry(query, tuple(params), fetch='all')
    
    def create_tables(self):
        """Create all required tables with proper schema."""
        tables = [
            """
            CREATE TABLE IF NOT EXISTS annotations (
                id VARCHAR(36) PRIMARY KEY,
                sensor_id VARCHAR(100) NOT NULL,
                start_timestamp TIMESTAMP NOT NULL,
                end_timestamp TIMESTAMP NOT NULL,
                vehicle_type VARCHAR(50) NOT NULL,
                action VARCHAR(50) NOT NULL,
                location VARCHAR(100),
                confidence FLOAT DEFAULT 1.0,
                metadata TEXT,
                status VARCHAR(20) DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_sensor_time (sensor_id, start_timestamp, end_timestamp),
                INDEX idx_vehicle_type (vehicle_type),
                INDEX idx_status (status)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS vehicle_types (
                type_id VARCHAR(50) PRIMARY KEY,
                display_name VARCHAR(100) NOT NULL,
                category VARCHAR(50) NOT NULL,
                subclass VARCHAR(50),
                metadata TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS processing_windows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sensor_id VARCHAR(100) NOT NULL,
                start_timestamp TIMESTAMP NOT NULL,
                end_timestamp TIMESTAMP NOT NULL,
                status VARCHAR(20) DEFAULT 'pending',
                processing_started_at TIMESTAMP,
                processing_completed_at TIMESTAMP,
                error_message TEXT,
                retry_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(sensor_id, start_timestamp, end_timestamp)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS feature_extractions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                annotation_id VARCHAR(36) NOT NULL,
                feature_type VARCHAR(50) NOT NULL,
                feature_data BLOB NOT NULL,
                extraction_params TEXT,
                extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (annotation_id) REFERENCES annotations(id),
                INDEX idx_annotation_feature (annotation_id, feature_type)
            )
            """
        ]
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            for table_sql in tables:
                # Adjust SQL syntax for SQLite
                if not self.is_postgres:
                    table_sql = table_sql.replace('VARCHAR', 'TEXT')
                    table_sql = table_sql.replace('TIMESTAMP', 'DATETIME')
                    table_sql = table_sql.replace('FLOAT', 'REAL')
                    table_sql = table_sql.replace('INDEX ', 'CREATE INDEX IF NOT EXISTS ')
                    table_sql = table_sql.replace('AUTOINCREMENT', 'AUTOINCREMENT')
                
                try:
                    cursor.execute(table_sql)
                    logger.info(f"Created/verified table")
                except Exception as e:
                    logger.warning(f"Table creation warning: {str(e)}")
    
    def get_processing_status(self, sensor_id: str) -> Dict[str, Any]:
        """Get processing status and statistics for a sensor."""
        query = """
        SELECT 
            COUNT(*) as total_windows,
            SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
            SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
            SUM(CASE WHEN status = 'processing' THEN 1 ELSE 0 END) as processing,
            MIN(start_timestamp) as earliest_window,
            MAX(end_timestamp) as latest_window,
            MAX(processing_completed_at) as last_processed_at
        FROM processing_windows
        WHERE sensor_id = %s
        """
        
        if not self.is_postgres:
            query = query.replace('%s', '?')
            
        result = self.execute_with_retry(query, (sensor_id,), fetch='one')
        
        return {
            'sensor_id': sensor_id,
            'total_windows': result['total_windows'] or 0,
            'completed': result['completed'] or 0,
            'failed': result['failed'] or 0,
            'processing': result['processing'] or 0,
            'earliest_window': result['earliest_window'],
            'latest_window': result['latest_window'],
            'last_processed_at': result['last_processed_at']
        }
    
    def mark_window_as_processed(self, sensor_id: str, start_time: datetime,
                               end_time: datetime, status: str = 'completed',
                               error_message: Optional[str] = None):
        """Mark a processing window as completed or failed."""
        query = """
        UPDATE processing_windows
        SET status = %s, 
            processing_completed_at = %s,
            error_message = %s
        WHERE sensor_id = %s 
            AND start_timestamp = %s 
            AND end_timestamp = %s
        """
        
        if not self.is_postgres:
            query = query.replace('%s', '?')
            
        params = (status, datetime.utcnow(), error_message, 
                 sensor_id, start_time, end_time)
        
        rows_affected = self.execute_with_retry(query, params)
        
        if rows_affected == 0:
            # Insert if not exists
            insert_query = """
            INSERT INTO processing_windows 
            (sensor_id, start_timestamp, end_timestamp, status, 
             processing_completed_at, error_message)
            VALUES (%s, %s, %s, %s, %s, %s)
            """
            if not self.is_postgres:
                insert_query = insert_query.replace('%s', '?')
                
            self.execute_with_retry(insert_query, 
                                  (sensor_id, start_time, end_time, status,
                                   datetime.utcnow(), error_message))