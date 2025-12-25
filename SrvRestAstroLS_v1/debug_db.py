import asyncio
import os
import sys

# Add the current directory to sys.path so we can import from services
sys.path.append(os.getcwd())

from services.db_pg import connect_db
from globalVar import DB_URL, DB_PG_IP, DB_PG_PORT, DB_PG_USER, DB_PG_PASS, DB_PG_WORKFLOW_AI

async def main():
    print(f"Debug: DB_URL={DB_URL}")
    print(f"Debug: IP={DB_PG_IP}, PORT={DB_PG_PORT}, USER={DB_PG_USER}, DB={DB_PG_WORKFLOW_AI}")
    
    try:
        print("Attempting to connect to DB via connect_db()...")
        conn = await connect_db(connect_timeout=5.0)
        print("Successfully connected!")
        
        val = await conn.fetchval("SELECT 1")
        print(f"Query 'SELECT 1' returned: {val}")
        
        await conn.close()
        print("Connection closed.")
    except Exception as e:
        print(f"Connection failed: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
