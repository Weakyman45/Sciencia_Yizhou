#!/usr/bin/env python3
from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

import requests

SEARCH_URL = "https://itunes.apple.com/search"
RSS_URL_TMPL = "https://itunes.apple.com/{country}/rss/customerreviews/page={page}/id={app_id}/sortby=mostrecent/json"


@dataclass
class Config:
    target_reviews: int = 20_000
    out_jsonl: str = "apple_reviews_us.jsonl"

    seen_keys_path: str = "apple_seen_keys_us.txt"
    enable_resume: bool = True

    countries: Tuple[str, ...] = ("us",)   # <-- US only

    search_terms: Tuple[str, ...] = (
        "game", "music", "photo", "fitness", "calendar", "ai", "chat", "learn",
        "finance", "weather", "maps", "camera", "notes", "video", "shopping",
        "travel", "food", "health", "sleep", "scanner", "budget", "vpn",
    )
    search_limit: int = 200
    max_pages_per_app: int = 10
    min_s_between_search_calls: float = 3.5
    min_s_between_rss_calls: float = 0.4


def safe_get(d: dict, keys: List[str], default=None):
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def load_seen_keys(path: str) -> Set[str]:
    p = Path(path)
    if not p.exists():
        return set()
    return set(line.strip() for line in p.read_text(encoding="utf-8").splitlines() if line.strip())


def append_seen_key(path: str, key: str) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(key + "\n")


def discover_app_ids(cfg: Config, session: requests.Session) -> Iterable[int]:
    """
    Yield many app trackIds from iTunes Search API across terms and countries.
    """
    seen_app_ids: Set[int] = set()

    terms = list(cfg.search_terms)
    random.shuffle(terms)
    countries = list(cfg.countries)
    random.shuffle(countries)

    for country in countries:
        for term in terms:
            r = session.get(
                SEARCH_URL,
                params={"term": term, "country": country, "entity": "software", "limit": cfg.search_limit},
                timeout=30,
            )
            r.raise_for_status()
            data = r.json()

            for item in data.get("results", []):
                track_id = item.get("trackId")
                if isinstance(track_id, int) and track_id not in seen_app_ids:
                    seen_app_ids.add(track_id)
                    yield track_id

            time.sleep(cfg.min_s_between_search_calls)


def parse_reviews_from_feed(feed_json: dict) -> List[Dict]:
    """
    Parse RSS JSON into a list of review dicts.
    Heuristic: review entries contain 'im:rating'.
    """
    entries = safe_get(feed_json, ["feed", "entry"], default=[])
    if not isinstance(entries, list) or not entries:
        return []

    reviews: List[Dict] = []
    for e in entries:
        rating = safe_get(e, ["im:rating", "label"])
        if rating is None:
            continue

        # A reasonably stable review identifier:
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

        reviews.append(
            {
                "review_id": str(review_id) if review_id is not None else None,
                "author": author,
                "title": title,
                "text": body,
                "rating": rating_int,
                "created_at": created_at,
                "app_version": app_version,
                "raw": e,  # keep raw in case you discover useful fields later
            }
        )

    return reviews


def fetch_reviews_for_app(cfg: Config, session: requests.Session, country: str, app_id: int) -> List[Dict]:
    """
    Fetch up to cfg.max_pages_per_app pages of RSS reviews for an app.
    Stop early if empty/404.
    """
    all_reviews: List[Dict] = []
    for page in range(1, cfg.max_pages_per_app + 1):
        url = RSS_URL_TMPL.format(country=country, page=page, app_id=app_id)
        r = session.get(url, timeout=30)
        if r.status_code == 404:
            break
        r.raise_for_status()

        feed = r.json()
        page_reviews = parse_reviews_from_feed(feed)
        if not page_reviews:
            break

        all_reviews.extend(page_reviews)
        time.sleep(cfg.min_s_between_rss_calls)

    return all_reviews


def main():
    cfg = Config()
    session = requests.Session()

    seen_keys: Set[str] = load_seen_keys(cfg.seen_keys_path) if cfg.enable_resume else set()
    print(f"Loaded seen keys: {len(seen_keys)}")

    out = open(cfg.out_jsonl, "a", encoding="utf-8")

    def unique_count() -> int:
        return len(seen_keys)

    for app_id in discover_app_ids(cfg, session):
        if unique_count() >= cfg.target_reviews:
            break

        for country in cfg.countries:
            if unique_count() >= cfg.target_reviews:
                break

            try:
                reviews = fetch_reviews_for_app(cfg, session, country, app_id)
            except Exception:
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
                if cfg.enable_resume:
                    append_seen_key(cfg.seen_keys_path, key)

                record = {
                    "platform": "apple",
                    "country": country,
                    "app_id": app_id,
                    "review_id": rid,
                    "author": rv.get("author"),
                    "title": rv.get("title"),
                    "text": rv.get("text"),
                    "rating": rv.get("rating"),
                    "created_at": rv.get("created_at"),
                    "app_version": rv.get("app_version"),
                    "raw": rv.get("raw"),
                }
                out.write(json.dumps(record, ensure_ascii=False) + "\n")

                if unique_count() % 500 == 0:
                    print(f"Collected {unique_count()} unique Apple reviews...")

                if unique_count() >= cfg.target_reviews:
                    break

    out.close()
    print(f"Done. Total unique Apple reviews collected: {unique_count()}")
    print(f"Output: {cfg.out_jsonl}")


if __name__ == "__main__":
    main()