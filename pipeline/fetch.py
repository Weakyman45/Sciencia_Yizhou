import json
import random
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Set, Optional, Iterable

import requests

try:
    from google_play_scraper import reviews as gplay_reviews, Sort
    GOOGLE_PLAY_AVAILABLE = True
except ImportError:
    GOOGLE_PLAY_AVAILABLE = False

logger = logging.getLogger(__name__)

ITUNES_SEARCH_URL = "https://itunes.apple.com/search"
ITUNES_RSS_URL_TMPL = "https://itunes.apple.com/{country}/rss/customerreviews/page={page}/id={app_id}/sortby=mostrecent/json"


def safe_get(d: dict, keys: List[str], default=None):
    """Safely traverse nested dictionary."""
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def load_seen_keys(path: str) -> Set[str]:
    """Load previously seen review keys for resume functionality."""
    p = Path(path)
    if not p.exists():
        return set()
    return set(line.strip() for line in p.read_text(encoding="utf-8").splitlines() if line.strip())


def append_seen_key(path: str, key: str) -> None:
    """Append a new seen key to the resume file."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(key + "\n")


class DateTimeEncoder(json.JSONEncoder):
    """JSON encoder that handles datetime objects."""
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

# Google Play Fetcher
def fetch_google_reviews(
    app_id: str,
    app_name: str,
    target_count: int = 10000,
    lang: str = 'en',
    country: str = 'us'
) -> List[Dict[str, Any]]:
    if not GOOGLE_PLAY_AVAILABLE:
        logger.error("google-play-scraper not installed. Run: pip install google-play-scraper")
        return []
    
    logger.info(f"Fetching {target_count} Google Play reviews for {app_name} ({app_id})...")
    
    try:
        result, continuation_token = gplay_reviews(
            app_id,
            lang=lang,
            country=country,
            sort=Sort.NEWEST,
            count=target_count
        )
        
        logger.info(f"Successfully fetched {len(result)} reviews from Google Play")
        return result
        
    except Exception as e:
        logger.error(f"Error fetching Google Play reviews: {e}")
        return []


# Apple App Store Fetcher
def discover_apple_app_ids(
    session: requests.Session,
    search_terms: List[str],
    countries: List[str],
    search_limit: int = 200,
    min_delay: float = 3.5
) -> Iterable[int]:
    seen_app_ids: Set[int] = set()
    
    terms = list(search_terms)
    random.shuffle(terms)
    countries_list = list(countries)
    random.shuffle(countries_list)
    
    for country in countries_list:
        for term in terms:
            try:
                r = session.get(
                    ITUNES_SEARCH_URL,
                    params={
                        "term": term,
                        "country": country,
                        "entity": "software",
                        "limit": search_limit
                    },
                    timeout=30
                )
                r.raise_for_status()
                data = r.json()
                
                for item in data.get("results", []):
                    track_id = item.get("trackId")
                    if isinstance(track_id, int) and track_id not in seen_app_ids:
                        seen_app_ids.add(track_id)
                        yield track_id
                
                time.sleep(min_delay)
                
            except Exception as e:
                logger.warning(f"Error searching for '{term}' in {country}: {e}")
                continue


def parse_apple_reviews_from_feed(feed_json: dict) -> List[Dict]:
    entries = safe_get(feed_json, ["feed", "entry"], default=[])
    if not isinstance(entries, list) or not entries:
        return []
    
    reviews: List[Dict] = []
    for e in entries:
        rating = safe_get(e, ["im:rating", "label"])
        if rating is None:
            continue
        
        review_id = safe_get(e, ["id", "label"]) or safe_get(e, ["link", "attributes", "href"])
        title = safe_get(e, ["title", "label"])
        body = safe_get(e, ["content", "label"])
        author = safe_get(e, ["author", "name", "label"])
        created_at = safe_get(e, ["updated", "label"]) or safe_get(e, ["published", "label"])
        app_version = safe_get(e, ["im:version", "label"])
        
        try:
            rating_int = int(str(rating))
        except Exception:
            rating_int = None
        
        reviews.append({
            "review_id": str(review_id) if review_id is not None else None,
            "author": author,
            "title": title,
            "text": body,
            "rating": rating_int,
            "created_at": created_at,
            "app_version": app_version,
            "raw": e,
        })
    
    return reviews


def fetch_apple_reviews_for_app(
    session: requests.Session,
    country: str,
    app_id: int,
    max_pages: int = 10,
    min_delay: float = 0.4
) -> List[Dict]:
    all_reviews: List[Dict] = []
    
    for page in range(1, max_pages + 1):
        url = ITUNES_RSS_URL_TMPL.format(country=country, page=page, app_id=app_id)
        
        try:
            r = session.get(url, timeout=30)
            if r.status_code == 404:
                break
            r.raise_for_status()
            
            feed = r.json()
            page_reviews = parse_apple_reviews_from_feed(feed)
            
            if not page_reviews:
                break
            
            all_reviews.extend(page_reviews)
            time.sleep(min_delay)
            
        except Exception as e:
            logger.debug(f"Error fetching page {page} for app {app_id}: {e}")
            break
    
    return all_reviews


def fetch_apple_reviews(
    config: Dict[str, Any],
    seen_keys: Optional[Set[str]] = None,
    seen_keys_path: Optional[str] = None
) -> List[Dict[str, Any]]:
    target_reviews = config.get('target_reviews', 20000)
    countries = config.get('countries', ['us'])
    search_terms = config.get('search_terms', [])
    search_limit = config.get('search_limit', 200)
    max_pages = config.get('max_pages_per_app', 10)
    
    if seen_keys is None:
        seen_keys = set()
    
    session = requests.Session()
    all_records: List[Dict[str, Any]] = []
    
    logger.info(f"Starting Apple App Store fetch (target: {target_reviews} reviews)...")
    
    # Get pipeline delays from parent config if available
    min_search_delay = config.get('min_delay_between_search_calls', 3.5)
    min_rss_delay = config.get('min_delay_between_rss_calls', 0.4)
    
    for app_id in discover_apple_app_ids(
        session, search_terms, countries, search_limit, min_search_delay
    ):
        if len(all_records) >= target_reviews:
            break
        
        for country in countries:
            if len(all_records) >= target_reviews:
                break
            
            try:
                reviews = fetch_apple_reviews_for_app(
                    session, country, app_id, max_pages, min_rss_delay
                )
            except Exception as e:
                logger.debug(f"Error fetching app {app_id}: {e}")
                continue
            
            for rv in reviews:
                rid = rv.get("review_id")
                if not rid:
                    continue
                
                # Global dedupe key (country + app_id + review_id)
                key = f"{country}|{app_id}|{rid}"
                if key in seen_keys:
                    continue
                
                seen_keys.add(key)
                if seen_keys_path:
                    append_seen_key(seen_keys_path, key)
                
                record = {
                    "platform": "apple_app_store",
                    "country": country,
                    "app_id": app_id,
                    "review_id": rid,
                    "author": rv.get("author"),
                    "title": rv.get("title"),
                    "text": rv.get("text"),
                    "rating": rv.get("rating"),
                    "created_at": rv.get("created_at"),
                    "app_version": rv.get("app_version"),
                }
                all_records.append(record)
                
                if len(all_records) % 500 == 0:
                    logger.info(f"Collected {len(all_records)} Apple reviews...")
                
                if len(all_records) >= target_reviews:
                    break
    
    logger.info(f"Successfully fetched {len(all_records)} Apple App Store reviews")
    return all_records

# Main Fetch Orchestrator
def fetch_all(config: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    sources = config.get('sources', {})
    resume_config = config.get('resume', {})
    pipeline_config = config.get('pipeline', {})
    
    results = {
        'google_play': [],
        'apple_app_store': []
    }
    google_config = sources.get('google_play', {})
    if google_config.get('enabled', False):
        reviews = fetch_google_reviews(
            app_id=google_config.get('app_id', 'com.reddit.frontpage'),
            app_name=google_config.get('app_name', 'Reddit'),
            target_count=google_config.get('target_reviews', 10000),
            lang=google_config.get('language', 'en'),
            country=google_config.get('country', 'us')
        )
        for rv in reviews:
            record = {
                "platform": "google_play",
                "country": google_config.get('country', 'us'),
                "app_id": google_config.get('app_id'),
                "app_name": google_config.get('app_name'),
                "review_id": rv.get('reviewId'),
                "author": rv.get('userName'),
                "title": None,  # Google Play doesn't have titles
                "text": rv.get('content'),
                "rating": rv.get('score'),
                "created_at": rv.get('at'),
                "app_version": rv.get('reviewCreatedVersion') or rv.get('appVersion'),
                "thumbs_up_count": rv.get('thumbsUpCount'),
                "developer_reply": rv.get('replyContent'),
                "developer_reply_date": rv.get('repliedAt'),
            }
            results['google_play'].append(record)
    
    # Fetch Apple App Store reviews
    apple_config = sources.get('apple_app_store', {})
    if apple_config.get('enabled', False):
        seen_keys = set()
        seen_keys_path = None
        
        if resume_config.get('enabled', False):
            seen_keys_path = resume_config.get('seen_keys_file', 'data/apple_seen_keys.txt')
            seen_keys = load_seen_keys(seen_keys_path)
            logger.info(f"Loaded {len(seen_keys)} previously seen Apple review keys")
        
        # Add pipeline delays to apple config
        apple_config['min_delay_between_search_calls'] = pipeline_config.get(
            'min_delay_between_search_calls', 3.5
        )
        apple_config['min_delay_between_rss_calls'] = pipeline_config.get(
            'min_delay_between_rss_calls', 0.4
        )
        
        results['apple_app_store'] = fetch_apple_reviews(
            apple_config,
            seen_keys=seen_keys,
            seen_keys_path=seen_keys_path
        )
    
    # Log summary
    logger.info(
        f"Fetch complete: {len(results['google_play'])} Google Play, "
        f"{len(results['apple_app_store'])} Apple App Store reviews"
    )
    
    return results