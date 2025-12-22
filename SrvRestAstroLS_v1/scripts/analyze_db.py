import asyncio
import asyncpg
from globalVar import DB_SCHEMA, DB_URL

def _normalize_db_url(url: str) -> str:
    if url.startswith("postgresql+psycopg://"):
        return "postgresql://" + url.split("postgresql+psycopg://", 1)[1]
    if url.startswith("postgresql+asyncpg://"):
        return "postgresql://" + url.split("postgresql+asyncpg://", 1)[1]
    return url

async def analyze():
    url = _normalize_db_url(DB_URL)
    print(f"Connecting to {url}...")
    try:
        conn = await asyncpg.connect(
            url,
            server_settings={"search_path": DB_SCHEMA},
        )
    except Exception as e:
        print(f"Error connecting: {e}")
        return

    print("\n--- Tables ---")
    tables = await conn.fetch(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = $1
        ORDER BY table_name;
        """,
        DB_SCHEMA,
    )
    
    for t in tables:
        name = t['table_name']
        safe_schema = DB_SCHEMA.replace('"', '""')
        safe_name = name.replace('"', '""')
        count = await conn.fetchval(
            f'SELECT count(*) FROM "{safe_schema}"."{safe_name}"'
        )
        print(f"Table: {name} ({count} rows)")
        
        columns = await conn.fetch(
            """
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = $1 AND table_name = $2
            ORDER BY ordinal_position;
            """,
            DB_SCHEMA,
            name,
        )
        for c in columns:
            print(f"  - {c['column_name']} ({c['data_type']}, {'NULL' if c['is_nullable'] == 'YES' else 'NOT NULL'})")

    await conn.close()

if __name__ == "__main__":
    asyncio.run(analyze())
