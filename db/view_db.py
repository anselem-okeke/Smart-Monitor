# import sqlite3
# import os
#
# # Get absolute path to the DB file in the same directory as this script
# base_dir = os.path.dirname(os.path.abspath(__file__))
# db_path = os.path.join(base_dir, 'smart_factory_monitor.db')
#
# conn = sqlite3.connect(db_path)
# cursor = conn.cursor()
#
# # Show all table names
# cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
# tables = cursor.fetchall()
#
# print("Tables in the database:")
# for table in tables:
#     print(f"- {table[0]}")
#
# conn.close()


# import sqlite3
#
# db_path = "db/smart_factory_monitor.db"
#
# conn = sqlite3.connect(db_path)
# cursor = conn.cursor()
#
# # View all tables
# cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
# tables = cursor.fetchall()
# print("\n[Tables in DB]:")
# for t in tables:
#     print("-", t[0])
#
# # View rows in system_metrics
# print("\n[System Metrics Rows]:")
# cursor.execute("SELECT * FROM system_metrics ORDER BY timestamp DESC LIMIT 5;")
# rows = cursor.fetchall()
# for row in rows:
#     print(row)
#
# conn.close()

import sqlite3
import os

# Absolute path to DB (based on current script location)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.abspath(os.path.join(BASE_DIR, '../db/smart_factory_monitor.db'))

print(f"[DEBUG] Opening DB at: {DB_PATH}")

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Check tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()
print("Tables:", tables)

# View recent rows
cursor.execute("SELECT * FROM service_status ORDER BY timestamp DESC LIMIT 5;")
rows = cursor.fetchall()

print("\nLatest service_status entries:")
for row in rows:
    print(row)

conn.close()



