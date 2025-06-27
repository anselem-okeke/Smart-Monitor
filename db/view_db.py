import sqlite3
import os

# Get absolute path to the DB file in the same directory as this script
base_dir = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(base_dir, 'smart_factory_monitor.db')

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Show all table names
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()

print("Tables in the database:")
for table in tables:
    print(f"- {table[0]}")

conn.close()

