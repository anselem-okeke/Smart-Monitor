import sqlite3
import os

def initialize_db():
    # Get the directory where this script is located
    base_dir = os.path.dirname(os.path.abspath(__file__))

    db_path = os.path.join(base_dir, 'smart_factory_monitor.db')
    schema_path = os.path.join(base_dir, 'schema.sql')

    conn = None
    try:
        conn = sqlite3.connect(db_path)
        with open(schema_path, 'r') as f:
            conn.executescript(f.read())
        print(f"Database initialized at: {db_path}")
    except Exception as e:
        print(f"Error initializing database: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    initialize_db()


