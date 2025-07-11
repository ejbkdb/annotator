# backend/inspect_data.py
#!/usr/bin/env python3
"""
A simple script to fetch and display the first few rows from a QuestDB table
to inspect the raw data, especially the format of the stored timestamps.
"""

import psycopg2
from psycopg2.extras import RealDictCursor
import os
from dotenv import load_dotenv

# --- Configuration ---
# Load environment variables from a .env file if it exists
load_dotenv()
# The name of the table you want to inspect
TABLE_TO_INSPECT = "my_hardcoded_test" 
# ---------------------


def inspect_table_head():
    """Connects to QuestDB and fetches the first 5 rows of the specified table."""
    
    # Use connection details from environment variables or fall back to defaults
    conn_details = {
        "host": os.getenv("QUESTDB_HOST", "localhost"),
        "port": int(os.getenv("QUESTDB_PORT", "8812")),
        "user": os.getenv("QUESTDB_USER", "admin"),
        "password": os.getenv("QUESTDB_PASSWORD", "quest"),
        "database": os.getenv("QUESTDB_DATABASE", "qdb")
    }
    
    conn = None
    try:
        print(f"Attempting to connect to QuestDB at {conn_details['host']}:{conn_details['port']}...")
        conn = psycopg2.connect(**conn_details)
        # Use RealDictCursor to get results as dictionaries (like key-value pairs)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        print(f"Connection successful. Fetching first 5 rows from table: '{TABLE_TO_INSPECT}'...")
        
        # Construct and execute the query
        query = f"SELECT * FROM '{TABLE_TO_INSPECT}' LIMIT 5"
        cur.execute(query)
        
        # Fetch all the results
        results = cur.fetchall()
        
        print("-" * 70)
        if not results:
            print(f"❌ No results found. Is the table '{TABLE_TO_INSPECT}' empty or does it not exist?")
        else:
            print(f"✅ Found {len(results)} rows. Displaying raw data:")
            for i, row in enumerate(results, 1):
                print(f"Row {i}:")
                # Pretty-print each key-value pair in the row
                for key, value in row.items():
                    print(f"  - {key}: {value}")
                # Check the type of the timestamp for extra debugging
                if 'ts' in row:
                    print(f"  - (Timestamp Python Type: {type(row['ts'])})")

        print("-" * 70)

        # Close the cursor
        cur.close()
        
    except psycopg2.Error as e:
        print(f"❌ Database Error: {e}")
        print("\n🔧 Troubleshooting:")
        print("  - Is the QuestDB container running? (check with 'docker ps' or 'podman ps')")
        print(f"  - Are the connection details correct for your environment? (Host: {conn_details['host']})")
        print(f"  - Does the table '{TABLE_TO_INSPECT}' exist?")

    finally:
        if conn is not None:
            conn.close()
            print("Connection closed.")


if __name__ == "__main__":
    inspect_table_head()