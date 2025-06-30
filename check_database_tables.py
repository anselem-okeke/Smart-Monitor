import sqlite3

conn = sqlite3.connect("db/smart_factory_monitor.db")
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()
print("Tables:", tables)
conn.close()
