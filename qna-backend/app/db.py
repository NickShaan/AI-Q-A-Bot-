# app/db.py
import os
from datetime import datetime
from dotenv import load_dotenv

# --- Load envs early
print("[db] Loading environment variables...")
load_dotenv()

# --- Read DB parts
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "root")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "")

# --- Build URLs
ASYNC_URL = None   
SYNC_URL  = None   

if DB_NAME:
    ASYNC_URL = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    SYNC_URL  = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

def _mask_url(url: str) -> str:
    if not url:
        return ""
    try:
        prefix, rest = url.split("://", 1)
        creds, tail  = rest.split("@", 1)
        if ":" in creds:
            user, _pwd = creds.split(":", 1)
            creds_masked = f"{user}:********"
        else:
            creds_masked = creds
        return f"{prefix}://{creds_masked}@{tail}"
    except Exception:
        return url

print(f"[db] DB_NAME          = {DB_NAME or '(empty)'}")
print(f"[db] ASYNC_URL (masked)= {_mask_url(ASYNC_URL) if ASYNC_URL else '(none)'}")
print(f"[db] SYNC_URL  (masked)= {_mask_url(SYNC_URL)  if SYNC_URL  else '(none)'}")


from sqlalchemy import MetaData, Table, Column, Integer, Text, TIMESTAMP, create_engine
from databases import Database


metadata = MetaData()

qa_table = Table(
    "qa_history",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("question", Text, nullable=False),
    Column("answer", Text, nullable=False),
    Column("created_at", TIMESTAMP, nullable=False, default=datetime.utcnow),
)


database = Database(ASYNC_URL) if ASYNC_URL else None

def init_db(create_tables: bool = True):
    """
    Synchronously ensure tables exist using a **sync** engine (no +asyncpg).
    This avoids the 'greenlet_spawn / await_only()' error.
    """
    print("[db.init_db] Enter")
    if not SYNC_URL:
        print("[db.init_db] SYNC_URL missing (DB_NAME empty) -> skipping table creation")
        return

    print("[db.init_db] Creating sync engine for DDL...")

    engine = create_engine(SYNC_URL, echo=False, future=True)

    if create_tables:
        print("[db.init_db] Calling metadata.create_all(engine)...")
        metadata.create_all(engine)
        print("[db.init_db] Tables ensured (qa_history).")
    else:
        print("[db.init_db] create_tables=False -> skipped create_all")

    print("[db.init_db] Exit")

async def save_qa(question: str, answer: str):
    """
    Async insert using `databases`. No-op if database is None.
    """
    print("[db.save_qa] Enter")
    if database is None:
        print("[db.save_qa] 'database' is None -> skipping insert")
        return None

    try:
        query = qa_table.insert().values(question=question, answer=answer)
        print("[db.save_qa] Executing insert...")
        inserted_id = await database.execute(query)
        print(f"[db.save_qa] Insert OK (id={inserted_id})")
        return inserted_id
    except Exception as e:
        print(f"[db.save_qa] Insert FAILED: {e}")
        raise
    finally:
        print("[db.save_qa] Exit")
