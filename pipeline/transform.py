import logging
import hashlib
import re
from datetime import datetime
from typing import List, Dict, Any, Optional, Set, Tuple, Union

logger = logging.getLogger(__name__)


def clean_text(text: Optional[str]) -> str:
    """Clean and normalize text content."""
    if not text:
        return ''
    
    text = str(text)
    text = text.strip()
    text = re.sub(r'\s+', ' ', text)
    text = text.replace('\x00', '')
    
    return text


def parse_date(date_value: Any) -> Optional[str]:
    """Parse various date formats to ISO8601 string."""
    if date_value is None:
        return None
    
    if isinstance(date_value, datetime):
        return date_value.isoformat()
    
    if isinstance(date_value, str):
        return date_value
    
    return str(date_value)


def compute_content_hash(content: str) -> str:
    """Compute a hash of review content for duplicate detection."""
    normalized = content.lower().strip()
    return hashlib.md5(normalized.encode()).hexdigest()


def normalize_google_review(record: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a Google Play review record to the unified schema."""
    return {
        'platform': 'google_play',
        'source_review_id': str(record.get('review_id', '')),
        'app_id': record.get('app_id'),
        'app_name': record.get('app_name'),
        'country': record.get('country', 'us'),
        'author_name': record.get('author', 'Unknown'),
        'title': None,
        'content': clean_text(record.get('text', '')),
        'rating': int(record.get('rating', 0)) if record.get('rating') else None,
        'app_version': record.get('app_version'),
        'review_date': parse_date(record.get('created_at')),
        'thumbs_up_count': record.get('thumbs_up_count'),
        'developer_reply': record.get('developer_reply'),
        'developer_reply_date': parse_date(record.get('developer_reply_date')),
    }


def normalize_apple_review(record: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize an Apple App Store review record to the unified schema."""
    return {
        'platform': 'apple_app_store',
        'source_review_id': str(record.get('review_id', '')),
        'app_id': str(record.get('app_id', '')),
        'app_name': None,
        'country': record.get('country', 'us'),
        'author_name': record.get('author', 'Unknown'),
        'title': clean_text(record.get('title', '')),
        'content': clean_text(record.get('text', '')),
        'rating': int(record.get('rating')) if record.get('rating') else None,
        'app_version': record.get('app_version'),
        'review_date': parse_date(record.get('created_at')),
        'thumbs_up_count': None,
        'developer_reply': None,
        'developer_reply_date': None,
    }


def validate_review(review: Dict[str, Any]) -> bool:
    """Validate that a review has all required fields."""
    if not review.get('source_review_id'):
        return False
    
    if not review.get('content'):
        return False
    
    rating = review.get('rating')
    if rating is None or not (1 <= rating <= 5):
        return False
    
    if not review.get('platform'):
        return False
    
    return True


def transform_reviews(
    raw_data: Dict[str, List[Dict[str, Any]]],
    return_stats: bool = False
) -> Union[List[Dict[str, Any]], Tuple[List[Dict[str, Any]], Dict[str, Any]]]:
    normalized_reviews = []
    content_hashes: Set[str] = set()
    
    stats = {
        'total': 0,
        'valid': 0,
        'invalid': 0,
        'duplicate_content': 0,
        'missing_app_version': 0,
        'rating_distribution': {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    }
    
    # Process Google Play reviews
    for record in raw_data.get('google_play', []):
        stats['total'] += 1
        
        try:
            normalized = normalize_google_review(record)
            
            if not validate_review(normalized):
                stats['invalid'] += 1
                logger.debug(f"Invalid Google review: {normalized.get('source_review_id')}")
                continue
            
            # Track missing app versions
            if not normalized.get('app_version'):
                stats['missing_app_version'] += 1
            
            # Track rating distribution
            rating = normalized.get('rating')
            if rating in stats['rating_distribution']:
                stats['rating_distribution'][rating] += 1
            
            # Check for duplicate content
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
    
    # Process Apple App Store reviews
    for record in raw_data.get('apple_app_store', []):
        stats['total'] += 1
        
        try:
            normalized = normalize_apple_review(record)
            
            if not validate_review(normalized):
                stats['invalid'] += 1
                logger.debug(f"Invalid Apple review: {normalized.get('source_review_id')}")
                continue
            
            # Track missing app versions
            if not normalized.get('app_version'):
                stats['missing_app_version'] += 1
            
            # Track rating distribution
            rating = normalized.get('rating')
            if rating in stats['rating_distribution']:
                stats['rating_distribution'][rating] += 1
            
            # Check for duplicate content
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
    
    if return_stats:
        return normalized_reviews, stats
    return normalized_reviews