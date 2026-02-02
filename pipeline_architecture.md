# Automated Data Ingestion Pipeline

## 1. Overview

### Data Sources

| Platform        | Approach                                    | Per-Run Target |
| --------------- | ------------------------------------------- | -------------- |
| Google Play     | Single app (Reddit: `com.reddit.frontpage`) | 1,000 reviews  |
| Apple App Store | Dynamic discovery via iTunes Search API     | 2,000 reviews  |

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         run_pipeline.py                             │
│                      (Orchestrator / Entry Point)                   │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                            config.yaml                              │
│         (App IDs, targets, schedule, monitoring settings)           │
└─────────────────────────────────────────────────────────────────────┘
                                   │
         ┌────────────┬────────────┼────────────┬────────────┐
         ▼            ▼            ▼            ▼            ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│  fetch.py    │ │ transform.py │ │   load.py    │ │  monitor.py  │
│              │ │              │ │              │ │              │
│ Google Play: │ │ • Normalize  │ │ • Insert DB  │ │ • Track time │
│ • Single app │ │ • Clean text │ │ • Dedup check│ │ • Compare    │
│              │ │ • Validate   │ │ • Batch ops  │ │   runs       │
│ Apple Store: │ │ • Stats      │ │              │ │ • Detect     │
│ • Discovery  │ │              │ │              │ │   anomalies  │
│ • RSS feeds  │ │              │ │              │ │ • Alert      │
└──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘
         │              │              │                   │
         └──────────────┴──────────────┴───────────────────┘
                                   │
                                   ▼
                        ┌──────────────────┐
                        │   database.py    │
                        │                  │
                        │ • SQLite conn    │
                        │ • Schema init    │
                        │ • Query helpers  │
                        └──────────────────┘
                                   │
                                   ▼
                        ┌──────────────────┐
                        │  data/reviews.db │
                        │                  │
                        │ • platforms      │
                        │ • apps           │
                        │ • reviews        │
                        │ • pipeline_runs  │
                        │ • monitoring_    │
                        │   alerts         │
                        └──────────────────┘
```

---

## 3. Directory Structure

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
│   ├── database.py             # Database utilities
│   └── monitor.py              # Monitoring & alerting module
├── data/
│   ├── reviews.db              # SQLite database
│   └── apple_seen_keys.txt     # Resume file for Apple fetcher
├── logs/
│   ├── pipeline.log            # Execution logs
│   └── monitoring_report.txt   # Generated monitoring reports
├── eda/
│   └── eda_visualizations.png  # EDA charts
└── .github/
    └── workflows/
        └── pipeline.yml        # GitHub Actions workflow
```

---

## 4. Scheduling & Frequency

### Available Intervals

| Frequency     | Cron Expression | Runs/Day | Use Case                                  |
| ------------- | --------------- | -------- | ----------------------------------------- |
| Daily         | `0 2 * * *`     | 1        | Baseline, low resource usage              |
| Every 6 hours | `0 */6 * * *`   | 4        | Moderate freshness                        |
| Every 4 hours | `0 */4 * * *`   | 6        | **Current default**                       |
| Every 2 hours | `0 */2 * * *`   | 12       | High freshness                            |
| Hourly        | `0 * * * *`     | 24       | Maximum freshness (watch for rate limits) |

### Configuration

In `config.yaml`:

```yaml
schedule:
  frequency: "every_4_hours"
```

In `.github/workflows/pipeline.yml`:

```yaml
on:
  schedule:
    - cron: "0 */4 * * *"
```

---

## 5. Monitoring & Observability

### Metrics Tracked Per Run

| Category         | Metrics                                                           |
| ---------------- | ----------------------------------------------------------------- |
| **Fetch**        | Reviews fetched (total, Google, Apple), retries, failures         |
| **Transform**    | Valid/invalid reviews, duplicate content count, missing fields    |
| **Load**         | Inserted, skipped (duplicates), errors                            |
| **Timing**       | Fetch duration, transform duration, load duration, total duration |
| **Data Quality** | Rating distribution (1-5 stars), missing app version count        |

### Anomaly Detection

The pipeline automatically detects and logs alerts for:

| Alert Type        | Threshold                                        | Severity |
| ----------------- | ------------------------------------------------ | -------- |
| `rate_drop`       | New records <50% of recent average               | Warning  |
| `duration_spike`  | Runtime >2x recent average                       | Warning  |
| `high_error_rate` | Errors >5% of fetched                            | Warning  |
| `rating_drift`    | Rating distribution shifts >10 percentage points | Info     |

### Database Tables

**`pipeline_runs`** — Stores metrics for each execution:

```sql
- run_id, started_at, completed_at, status
- reviews_fetched, reviews_fetched_google, reviews_fetched_apple
- reviews_inserted, reviews_skipped, errors
- fetch_duration_seconds, transform_duration_seconds, load_duration_seconds
- rating_1_count ... rating_5_count
- fetch_retries, fetch_failures
- error_message
```

**`monitoring_alerts`** — Stores detected anomalies:

```sql
- alert_id, run_id, alert_type, severity
- message, metric_name, metric_value, threshold_value
- created_at
```

### Viewing Monitoring Data

```bash
# Generate and display monitoring report
python run_pipeline.py --report
```

### SQL Queries for Manual Inspection

```sql
-- Recent pipeline runs
SELECT run_id, started_at, status, reviews_inserted,
       total_duration_seconds, errors
FROM pipeline_runs
ORDER BY run_id DESC
LIMIT 10;

-- Compare runs over time
SELECT DATE(started_at) as date,
       COUNT(*) as runs,
       SUM(reviews_inserted) as total_inserted,
       AVG(total_duration_seconds) as avg_duration
FROM pipeline_runs
WHERE status = 'success'
GROUP BY DATE(started_at)
ORDER BY date DESC;

-- Recent alerts
SELECT * FROM monitoring_alerts
ORDER BY created_at DESC
LIMIT 20;

-- Rating distribution trend
SELECT run_id, started_at,
       rating_1_count, rating_2_count, rating_3_count,
       rating_4_count, rating_5_count
FROM pipeline_runs
WHERE status = 'success'
ORDER BY run_id DESC
LIMIT 10;
```

---

## 6. Usage

### Basic Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Full pipeline run
python run_pipeline.py

# Dry run (no DB changes)
python run_pipeline.py --dry-run

# Google Play only (faster for testing)
python run_pipeline.py --google-only

# Apple App Store only
python run_pipeline.py --apple-only

# View monitoring report
python run_pipeline.py --report
```

### Local Scheduling (Cron)

```bash
# Run every 4 hours
0 */4 * * * cd /path/to/repo && python run_pipeline.py >> logs/cron.log 2>&1
```

### GitHub Actions

The workflow runs automatically based on the cron schedule. Manual triggers available via Actions tab with options for:

- Dry run
- Google only
- Apple only

---

## 7. Database Schema

### ERD

```
┌─────────────────────┐       ┌─────────────────────┐
│     platforms       │       │        apps         │
├─────────────────────┤       ├─────────────────────┤
│ PK  platform_id     │◄──┐   │ PK  app_id          │
│     name            │   │   │ FK  platform_id     │──┐
│     display_name    │   │   │     app_name        │  │
│     created_at      │   │   │     bundle_id       │  │
└─────────────────────┘   │   │     category        │  │
                          │   │     created_at      │  │
                          │   └─────────────────────┘  │
                          │                            │
                          │   ┌─────────────────────┐  │
                          │   │      reviews        │  │
                          │   ├─────────────────────┤  │
                          │   │ PK  review_id       │  │
                          └───│ FK  platform_id     │  │
                              │ FK  app_id          │◄─┘
                              │     source_review_id│
                              │     author_name     │
                              │     title           │  ← Apple only
                              │     content         │
                              │     rating          │
                              │     app_version     │
                              │     review_date     │
                              │     thumbs_up_count │  ← Google only
                              │     developer_reply │  ← Google only
                              │     developer_reply_date │
                              │     ingested_at     │
                              │     is_duplicate    │
                              │     sentiment_label │  ┐
                              │     labeled_at      │  ├─ ML fields
                              │     labeled_by      │  ┘
                              └─────────────────────┘

┌─────────────────────┐       ┌─────────────────────┐
│   pipeline_runs     │       │  monitoring_alerts  │
├─────────────────────┤       ├─────────────────────┤
│ PK  run_id          │◄──────│ FK  run_id          │
│     started_at      │       │ PK  alert_id        │
│     completed_at    │       │     alert_type      │
│     status          │       │     severity        │
│     reviews_fetched │       │     message         │
│     reviews_inserted│       │     metric_name     │
│     total_duration  │       │     metric_value    │
│     rating_1..5_cnt │       │     threshold_value │
│     ...             │       │     created_at      │
└─────────────────────┘       └─────────────────────┘
```
