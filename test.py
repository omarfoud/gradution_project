"""
Quick connectivity test for the SQL Server database.
Run this before starting the API to verify your credentials.

Usage:
    cp .env.example .env
    # fill in your SQL credentials in .env
    python test.py
"""
import os
import pyodbc
from dotenv import load_dotenv

load_dotenv()

server   = os.getenv("SQL_SERVER", "")
database = os.getenv("SQL_DATABASE", "")
username = os.getenv("SQL_USERNAME", "")
password = os.getenv("SQL_PASSWORD", "")
driver   = os.getenv("SQL_DRIVER", "ODBC Driver 18 for SQL Server")

missing = [k for k, v in {"SQL_SERVER": server, "SQL_DATABASE": database, "SQL_USERNAME": username, "SQL_PASSWORD": password}.items() if not v]
if missing:
    print(f"❌ Missing environment variables: {', '.join(missing)}")
    print("   Copy .env.example to .env and fill in your SQL Server credentials.")
    raise SystemExit(1)

connection_string = (
    f"DRIVER={{{driver}}};"
    f"SERVER={server};"
    f"DATABASE={database};"
    f"UID={username};"
    f"PWD={password};"
    "Encrypt=yes;"
    "TrustServerCertificate=yes;"
)

print(f"Attempting to connect to {server} / {database}...")

try:
    conn = pyodbc.connect(connection_string)
    print("✅ Connected successfully!")

    cursor = conn.cursor()
    cursor.execute("SELECT @@VERSION")
    row = cursor.fetchone()
    print(f"SQL Server: {row[0][:80]}...")

    conn.close()
except pyodbc.Error as e:
    print(f"❌ Connection failed: {e}")
