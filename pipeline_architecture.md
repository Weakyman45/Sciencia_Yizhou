# Automated Data Ingestion Pipeline

## 1. Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         run_pipeline.py                             │
│                      (Orchestrator / Entry Point)                   │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                            config.yaml                              │
│         (App IDs, search terms, targets, DB path, etc.)             │
└─────────────────────────────────────────────────────────────────────┘
                                   │
         ┌─────────────────────────┼─────────────────────────┐
         ▼                         ▼                         ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   fetch.py      │     │  transform.py   │     │    load.py      │
│                 │     │                 │     │                 │
│ Google Play:    │     │ • Normalize     │     │ • Insert to DB  │
│ • Single app    │ ──▶ │ • Clean text    │ ──▶ │ • Dedup check   │
│ • google-play-  │     │ • Validate      │     │ • Batch commits │
│   scraper       │     │ • Flag dupes    │     │                 │
│                 │     │                 │     │                 │
│ Apple Store:    │     │                 │     │                 │
│ • iTunes Search │     │                 │     │                 │
│ • RSS feeds     │     │                 │     │                 │
│ • Resume support│     │                 │     │                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                                         │
                                                         ▼
                                               ┌─────────────────┐
                                               │  database.py    │
                                               │                 │
                                               │ • SQLite conn   │
                                               │ • Schema init   │
                                               │ • Run tracking  │
                                               └─────────────────┘
                                                         │
                                                         ▼
                                               ┌─────────────────┐
                                               │ data/reviews.db │
                                               └─────────────────┘
```

---

## 2. Directory Structure

```
Sciencia_Yizhou/
├── config.yaml                 # Pipeline configuration
├── run_pipeline.py             # Main entry point
├── schema.sql                  # Database DDL
├── requirements.txt            # Python dependencies
├── pipeline/
│   ├── __init__.py
│   ├── fetch.py                # Data collection module
│   ├── transform.py            # Data normalization module
│   ├── load.py                 # Database loading module
│   └── database.py             # Database utilities
├── data/
│   ├── reviews.db              # SQLite database
│   └── apple_seen_keys.txt     # Resume file for Apple fetcher
├── logs/
│   └── pipeline.log            # Execution logs
├── eda/
│   └── eda_visualizations.png  # EDA charts
└── .github/
    └── workflows/
        └── pipeline.yml        # GitHub Actions workflow
```

---

## 3. Fetching Logic

### Google Play

Uses `google-play-scraper` library to fetch reviews from a single app:

### Apple App Store

Uses dynamic discovery via iTunes Search API + RSS feeds:

1. **Discover apps** — Search iTunes API with various terms (game, music, photo, etc.)
2. **Fetch reviews** — For each discovered app, fetch RSS feed pages
3. **Deduplicate** — Track seen review keys in `apple_seen_keys.txt` for resume

## 4. Usage

### Basic Run

```bash
# Install dependencies
pip install -r requirements.txt

# Run full pipeline
python run_pipeline.py

# Dry run (no DB changes)
python run_pipeline.py --dry-run

# Google Play only (faster for testing)
python run_pipeline.py --google-only

# Apple App Store only
python run_pipeline.py --apple-only
```

### Scheduled Runs

**Option A: Cron (Linux/Mac)**

```bash
# Run daily at 2:00 AM
0 2 * * * cd /path/to/repo && python run_pipeline.py >> logs/cron.log 2>&1
```

**Option B: GitHub Actions**

Push the `.github/workflows/pipeline.yml` file. The pipeline will run daily at 2:00 AM UTC and can be triggered manually from the Actions tab.

---

## 5. Configuration

Key settings in `config.yaml`:

---

## 6. Database Schema

See `schema.sql` and README for full ERD. Key tables:

## 7. Monitoring

Check pipeline runs:

```sql
SELECT * FROM pipeline_runs ORDER BY started_at DESC LIMIT 5;
```

Check review counts:

```sql
SELECT p.display_name, COUNT(*) as reviews
FROM reviews r
JOIN platforms p ON r.platform_id = p.platform_id
GROUP BY p.platform_id;
```
