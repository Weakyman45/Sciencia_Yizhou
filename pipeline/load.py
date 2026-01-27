import sqlite3
import logging
from typing import List, Dict, Any

from .database import get_platform_id, ensure_app_exists, review_exists

logger = logging.getLogger(__name__)


def insert_review(
    conn: sqlite3.Connection,
    review: Dict[str, Any],
    app_id: int,
    platform_id: int
) -> bool:
    try:
        conn.execute(
            """
            INSERT INTO reviews (
                app_id, platform_id, source_review_id, author_name, title,
                content, rating, app_version, review_date, thumbs_up_count,
                developer_reply, developer_reply_date, is_duplicate
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                app_id,
                platform_id,
                review['source_review_id'],
                review['author_name'],
                review.get('title'),
                review['content'],
                review['rating'],
                review.get('app_version'),
                review.get('review_date'),
                review.get('thumbs_up_count'),
                review.get('developer_reply'),
                review.get('developer_reply_date'),
                1 if review.get('is_duplicate', False) else 0
            )
        )
        return True
        
    except sqlite3.IntegrityError:
        return False


def load_reviews(
    conn: sqlite3.Connection,
    reviews: List[Dict[str, Any]],
    batch_size: int = 100
) -> Dict[str, int]:
    stats = {
        'total': len(reviews),
        'inserted': 0,
        'skipped': 0,
        'errors': 0
    }

    platform_cache: Dict[str, int] = {}
    app_cache: Dict[tuple, int] = {}
    
    for i, review in enumerate(reviews):
        try:
            platform_name = review['platform']
            app_bundle_id = str(review.get('app_id', 'unknown'))
            app_name = review.get('app_name') or f"App {app_bundle_id}"
            
            # Get or cache platform ID
            if platform_name not in platform_cache:
                platform_id = get_platform_id(conn, platform_name)
                if platform_id is None:
                    logger.error(f"Unknown platform: {platform_name}")
                    stats['errors'] += 1
                    continue
                platform_cache[platform_name] = platform_id
            platform_id = platform_cache[platform_name]
            
            # Get or cache app ID
            app_key = (platform_id, app_bundle_id)
            if app_key not in app_cache:
                db_app_id = ensure_app_exists(conn, platform_id, app_bundle_id, app_name)
                app_cache[app_key] = db_app_id
            db_app_id = app_cache[app_key]
            
            # Check if review already exists
            if review_exists(conn, platform_id, review['source_review_id']):
                stats['skipped'] += 1
                continue
            
            # Insert review
            if insert_review(conn, review, db_app_id, platform_id):
                stats['inserted'] += 1
            else:
                stats['skipped'] += 1
            
            # Commit in batches
            if (i + 1) % batch_size == 0:
                conn.commit()
                logger.debug(f"Committed batch at {i + 1} reviews")
                
        except Exception as e:
            logger.error(f"Error loading review {review.get('source_review_id')}: {e}")
            stats['errors'] += 1
    
    conn.commit()
    
    logger.info(
        f"Load complete: {stats['inserted']} inserted, "
        f"{stats['skipped']} skipped, {stats['errors']} errors"
    )
    
    return stats