import os
import pyodbc
from dotenv import load_dotenv

load_dotenv()

server = os.getenv("SQL_SERVER", "SQL9001.site4now.net")
database = os.getenv("SQL_DATABASE", "db_ac91b6_jobify")
username = os.getenv("SQL_USERNAME", "db_ac91b6_jobify_admin")
password = os.getenv("SQL_PASSWORD", "")

connection_string = (
    f"DRIVER={{ODBC Driver 18 for SQL Server}};"
    f"SERVER={server};"
    f"DATABASE={database};"
    f"UID={username};"
    f"PWD={password};"
    "Encrypt=yes;"
    "TrustServerCertificate=yes;"
)

print(f"Attempting to connect to {server}...")

try:
    conn = pyodbc.connect(connection_string)
    print("SUCCESS: Connected to the database successfully!")
    
    # Optional: Run a simple query to verify
    cursor = conn.cursor()
    cursor.execute("SELECT @@VERSION")
    row = cursor.fetchone()
    print(f"SQL Server Version: {row[0]}")
    
    conn.close()
except pyodbc.Error as e:
    print("FAILED: Could not connect to the database.")
    print(f"Error details: {e}")