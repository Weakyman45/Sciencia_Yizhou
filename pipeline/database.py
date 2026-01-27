import sqlite3
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)


def get_connection(db_path: str) -> sqlite3.Connection:
    # Ensure directory exists
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # Enable column access by name
    conn.execute("PRAGMA foreign_keys = ON")
    
    logger.debug(f"Connected to database: {db_path}")
    return conn


def init_schema(conn: sqlite3.Connection, schema_file: str) -> None:
    schema_path = Path(schema_file)
    
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_file}")
    
    with open(schema_path, 'r') as f:
        schema_sql = f.read()
    
    conn.executescript(schema_sql)
    conn.commit()
    
    logger.info(f"Database schema initialized from {schema_file}")


def get_platform_id(conn: sqlite3.Connection, platform_name: str) -> Optional[int]:
    cursor = conn.execute(
        "SELECT platform_id FROM platforms WHERE name = ?",
        (platform_name,)
    )
    row = cursor.fetchone()
    return row['platform_id'] if row else None


def ensure_app_exists(
    conn: sqlite3.Connection,
    platform_id: int,
    bundle_id: str,
    app_name: str,
    category: Optional[str] = None
) -> int:
    # Check if exists
    cursor = conn.execute(
        "SELECT app_id FROM apps WHERE platform_id = ? AND bundle_id = ?",
        (platform_id, bundle_id)
    )
    row = cursor.fetchone()
    
    if row:
        return row['app_id']
    
    # Create new app record
    cursor = conn.execute(
        """
        INSERT INTO apps (platform_id, app_name, bundle_id, category)
        VALUES (?, ?, ?, ?)
        """,
        (platform_id, app_name, bundle_id, category)
    )
    conn.commit()
    
    logger.debug(f"Created app record: {app_name} ({bundle_id})")
    return cursor.lastrowid


def get_review_count(conn: sqlite3.Connection, platform_id: Optional[int] = None) -> int:
    if platform_id:
        cursor = conn.execute(
            "SELECT COUNT(*) as count FROM reviews WHERE platform_id = ?",
            (platform_id,)
        )
    else:
        cursor = conn.execute("SELECT COUNT(*) as count FROM reviews")
    
    return cursor.fetchone()['count']


def review_exists(conn: sqlite3.Connection, platform_id: int, source_review_id: str) -> bool:
    cursor = conn.execute(
        "SELECT 1 FROM reviews WHERE platform_id = ? AND source_review_id = ?",
        (platform_id, source_review_id)
    )
    return cursor.fetchone() is not None


def start_pipeline_run(conn: sqlite3.Connection) -> int:
    cursor = conn.execute(
        "INSERT INTO pipeline_runs (started_at, status) VALUES (?, 'running')",
        (datetime.utcnow().isoformat(),)
    )
    conn.commit()
    return cursor.lastrowid


def complete_pipeline_run(
    conn: sqlite3.Connection,
    run_id: int,
    status: str,
    fetched: int,
    inserted: int,
    skipped: int,
    errors: int,
    error_message: Optional[str] = None
) -> None:
    conn.execute(
        """
        UPDATE pipeline_runs 
        SET completed_at = ?,
            status = ?,
            reviews_fetched = ?,
            reviews_inserted = ?,
            reviews_skipped = ?,
            errors = ?,
            error_message = ?
        WHERE run_id = ?
        """,
        (
            datetime.utcnow().isoformat(),
            status,
            fetched,
            inserted,
            skipped,
            errors,
            error_message,
            run_id
        )
    )
    conn.commit()