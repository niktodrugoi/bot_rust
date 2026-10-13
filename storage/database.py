import sqlite3
import logging

logger = logging.getLogger(__name__)

DB_FILE = "commits.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS processed_commits (
            commit_id TEXT PRIMARY KEY
        )
    """)
    conn.commit()
    conn.close()
    logger.info("Database initialized")

async def is_processed(commit_id: str) -> bool:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM processed_commits WHERE commit_id = ?", (commit_id,))
    exists = cursor.fetchone() is not None
    conn.close()
    return exists

async def mark_as_processed(commit_id: str):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO processed_commits (commit_id) VALUES (?)", (commit_id,))
    conn.commit()
    conn.close()
    logger.info(f"Marked commit {commit_id} as processed")