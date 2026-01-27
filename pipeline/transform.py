import logging
import hashlib
import re
from datetime import datetime
from typing import List, Dict, Any, Optional, Set

logger = logging.getLogger(__name__)


def clean_text(text: Optional[str]) -> str:
    if not text:
        return ''
    
    # Convert to string if needed
    text = str(text)
    
    # Strip leading/trailing whitespace
    text = text.strip()
    
    # Normalize whitespace (collapse multiple spaces/newlines)
    text = re.sub(r'\s+', ' ', text)
    
    # Remove null characters
    text = text.replace('\x00', '')
    
    return text


def parse_date(date_value: Any) -> Optional[str]:
    if date_value is None:
        return None
    
    if isinstance(date_value, datetime):
        return date_value.isoformat()
    
    if isinstance(date_value, str):
        return date_value
    
    return str(date_value)


def compute_content_hash(content: str) -> str:
    normalized = content.lower().strip()
    return hashlib.md5(normalized.encode()).hexdigest()


def normalize_google_review(record: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'platform': 'google_play',
        'source_review_id': str(record.get('review_id', '')),
        'app_id': record.get('app_id'),
        'app_name': record.get('app_name'),
        'country': record.get('country', 'us'),
        'author_name': record.get('author', 'Unknown'),
        'title': None,  # Google Play doesn't have titles
        'content': clean_text(record.get('text', '')),
        'rating': int(record.get('rating', 0)) if record.get('rating') else None,
        'app_version': record.get('app_version'),
        'review_date': parse_date(record.get('created_at')),
        'thumbs_up_count': record.get('thumbs_up_count'),
        'developer_reply': record.get('developer_reply'),
        'developer_reply_date': parse_date(record.get('developer_reply_date')),
    }


def normalize_apple_review(record: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'platform': 'apple_app_store',
        'source_review_id': str(record.get('review_id', '')),
        'app_id': str(record.get('app_id', '')),  # Apple uses numeric IDs
        'app_name': None,  # Not available from RSS feed
        'country': record.get('country', 'us'),
        'author_name': record.get('author', 'Unknown'),
        'title': clean_text(record.get('title', '')),
        'content': clean_text(record.get('text', '')),
        'rating': int(record.get('rating')) if record.get('rating') else None,
        'app_version': record.get('app_version'),
        'review_date': parse_date(record.get('created_at')),
        'thumbs_up_count': None,  # Apple doesn't provide this
        'developer_reply': None,  # Not available from RSS
        'developer_reply_date': None,
    }


def validate_review(review: Dict[str, Any]) -> bool:
    # Must have review ID
    if not review.get('source_review_id'):
        return False
    
    # Must have content
    if not review.get('content'):
        return False
    
    # Must have valid rating (1-5)
    rating = review.get('rating')
    if rating is None or not (1 <= rating <= 5):
        return False
    
    # Must have platform
    if not review.get('platform'):
        return False
    
    return True


def transform_reviews(
    raw_data: Dict[str, List[Dict[str, Any]]]
) -> List[Dict[str, Any]]:
    normalized_reviews = []
    content_hashes: Set[str] = set()
    
    stats = {
        'total': 0,
        'valid': 0,
        'invalid': 0,
        'duplicate_content': 0
    }
    
    for record in raw_data.get('google_play', []):
        stats['total'] += 1
        
        try:
            normalized = normalize_google_review(record)
            
            if not validate_review(normalized):
                stats['invalid'] += 1
                logger.debug(f"Invalid Google review: {normalized.get('source_review_id')}")
                continue
            
            content_hash = compute_content_hash(normalized['content'])
            if content_hash in content_hashes:
                normalized['is_duplicate'] = True
                stats['duplicate_content'] += 1
            else:
                normalized['is_duplicate'] = False
                content_hashes.add(content_hash)
            
            normalized_reviews.append(normalized)
            stats['valid'] += 1
            
        except Exception as e:
            stats['invalid'] += 1
            logger.warning(f"Error normalizing Google review: {e}")
    
    for record in raw_data.get('apple_app_store', []):
        stats['total'] += 1
        
        try:
            normalized = normalize_apple_review(record)
            
            if not validate_review(normalized):
                stats['invalid'] += 1
                logger.debug(f"Invalid Apple review: {normalized.get('source_review_id')}")
                continue
            
            content_hash = compute_content_hash(normalized['content'])
            if content_hash in content_hashes:
                normalized['is_duplicate'] = True
                stats['duplicate_content'] += 1
            else:
                normalized['is_duplicate'] = False
                content_hashes.add(content_hash)
            
            normalized_reviews.append(normalized)
            stats['valid'] += 1
            
        except Exception as e:
            stats['invalid'] += 1
            logger.warning(f"Error normalizing Apple review: {e}")
    
    logger.info(
        f"Transform complete: {stats['total']} total, {stats['valid']} valid, "
        f"{stats['invalid']} invalid, {stats['duplicate_content']} duplicate content"
    )
    
    return normalized_reviews