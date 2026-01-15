import json
from google_play_scraper import reviews, Sort
import pandas as pd
from datetime import datetime

APP_ID = 'com.reddit.frontpage'
TARGET_COUNT = 10000

print(f"🚀 Starting Google Play scrape for: {APP_ID}...")

result, continuation_token = reviews(
    APP_ID,
    lang='en',
    country='us', 
    sort=Sort.NEWEST, 
    count=TARGET_COUNT
)

print(f"✅ Fetched {len(result)} reviews from Google Play.")

class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

with open('google_play_10k.json', 'w', encoding='utf-8') as f:
    json.dump(result, f, indent=4, cls=DateTimeEncoder)

print("💾 Saved to 'google_play_10k.json'")