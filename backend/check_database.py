#!/usr/bin/env python3
"""
Quick script to check if data exists in your QuestDB database.
Run this from your backend directory.
"""

import psycopg2
from psycopg2.extras import RealDictCursor
import os
from dotenv import load_dotenv

load_dotenv()

# QuestDB connection details
QUESTDB_HOST = os.getenv("QUESTDB_HOST", "localhost")
QUESTDB_PORT = int(os.getenv("QUESTDB_PORT", "8812"))
QUESTDB_USER = os.getenv("QUESTDB_USER", "admin")
QUESTDB_PASSWORD = os.getenv("QUESTDB_PASSWORD", "quest")
QUESTDB_DATABASE = os.getenv("QUESTDB_DATABASE", "qdb")

def check_database():
    """Check database contents and structure"""
    try:
        # Connect to QuestDB
        conn = psycopg2.connect(
            host=QUESTDB_HOST,
            port=QUESTDB_PORT,
            user=QUESTDB_USER,
            password=QUESTDB_PASSWORD,
            database=QUESTDB_DATABASE
        )
        
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        print("🔍 QuestDB Database Inspection")
        print("=" * 50)
        
        # 1. List all tables
        print("\n📋 All Tables:")
        try:
            cur.execute("SHOW TABLES")
            tables = cur.fetchall()
            if tables:
                for table in tables:
                    print(f"  - {table['table']}")
            else:
                print("  ❌ No tables found!")
                return
        except Exception as e:
            print(f"  ❌ Error listing tables: {e}")
            return
        
        # 2. Check each table that looks like audio data
        audio_tables = []
        for table in tables:
            table_name = table['table']
            try:
                # Check if table has audio-like columns
                cur.execute(f"SELECT column_name, data_type FROM information_schema.columns WHERE table_name = '{table_name}'")
                columns = cur.fetchall()
                column_names = [col['column_name'] for col in columns]
                
                if 'amplitude' in column_names and 'ts' in column_names:
                    audio_tables.append(table_name)
                    print(f"\n🎵 Audio Table: {table_name}")
                    print(f"  Columns: {column_names}")
                    
                    # Count records
                    cur.execute(f"SELECT COUNT(*) as count FROM {table_name}")
                    count_result = cur.fetchone()
                    record_count = count_result['count'] if count_result else 0
                    print(f"  📊 Total records: {record_count:,}")
                    
                    if record_count > 0:
                        # Get time range
                        cur.execute(f"SELECT min(ts) as start_time, max(ts) as end_time FROM {table_name}")
                        time_range = cur.fetchone()
                        if time_range:
                            print(f"  ⏰ Time range: {time_range['start_time']} to {time_range['end_time']}")
                        
                        # Get sample data
                        cur.execute(f"SELECT * FROM {table_name} LIMIT 5")
                        samples = cur.fetchall()
                        print(f"  📝 Sample data:")
                        for i, sample in enumerate(samples, 1):
                            print(f"    {i}: ts={sample['ts']}, amplitude={sample['amplitude']}, file={sample.get('source_file', 'N/A')}")
                        
                        # Check data around the problematic time
                        print(f"\n🔍 Checking data around 2025-06-23T20:00:00...")
                        cur.execute(f"""
                            SELECT COUNT(*) as count 
                            FROM {table_name} 
                            WHERE ts >= '2025-06-23T20:00:00' 
                            AND ts <= '2025-06-23T20:00:10'
                        """)
                        range_count = cur.fetchone()
                        print(f"  📊 Records in 10-second window: {range_count['count']:,}")
                        
            except Exception as e:
                print(f"  ❌ Error checking table {table_name}: {e}")
        
        if not audio_tables:
            print("\n❌ No audio tables found! Your data might not be ingested yet.")
        else:
            print(f"\n✅ Found {len(audio_tables)} audio table(s): {', '.join(audio_tables)}")
        
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        print("\n🔧 Troubleshooting:")
        print(f"  - Is QuestDB running? Check: http://localhost:9000")
        print(f"  - Connection details: {QUESTDB_HOST}:{QUESTDB_PORT}")
        print(f"  - User: {QUESTDB_USER}")
        
    finally:
        if 'cur' in locals():
            cur.close()
        if 'conn' in locals():
            conn.close()

def test_specific_query():
    """Test the exact query that's failing"""
    try:
        conn = psycopg2.connect(
            host=QUESTDB_HOST,
            port=QUESTDB_PORT,
            user=QUESTDB_USER,
            password=QUESTDB_PASSWORD,
            database=QUESTDB_DATABASE
        )
        
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        print("\n🧪 Testing Problematic Query")
        print("=" * 50)
        
        # Test the query that was failing
        collection = "my_hardcoded_test"
        start_dt = "2025-06-23T20:00:00.000000+00:00"
        end_dt = "2025-06-23T20:00:10.000000+00:00"
        interval_us = 5000  # 5ms intervals
        
        sql = f"""
        SELECT 
            ts,
            min(amplitude) as min_val,
            max(amplitude) as max_val
        FROM {collection}
        WHERE ts >= '{start_dt}' AND ts < '{end_dt}'
        SAMPLE BY {interval_us}us
        ORDER BY ts
        """
        
        print(f"📝 Query:")
        print(sql)
        print()
        
        cur.execute(sql)
        results = cur.fetchall()
        
        print(f"✅ Query executed successfully!")
        print(f"📊 Returned {len(results)} rows")
        
        if results:
            print(f"📝 First few results:")
            for i, row in enumerate(results[:5]):
                print(f"  {i+1}: {row}")
        
    except Exception as e:
        print(f"❌ Query failed: {e}")
        print(f"💡 This might be the source of your 500 error!")
        
    finally:
        if 'cur' in locals():
            cur.close()
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    check_database()
    test_specific_query()