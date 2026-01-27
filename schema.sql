PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS platforms (
    platform_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(50) NOT NULL UNIQUE,
    display_name VARCHAR(100) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO platforms (name, display_name) VALUES 
    ('google_play', 'Google Play Store'),
    ('apple_app_store', 'Apple App Store');

CREATE TABLE IF NOT EXISTS apps (
    app_id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform_id INTEGER NOT NULL,
    app_name VARCHAR(255) NOT NULL,
    bundle_id VARCHAR(255) NOT NULL,
    category VARCHAR(100),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (platform_id) REFERENCES platforms(platform_id),
    UNIQUE (platform_id, bundle_id)
);

CREATE TABLE IF NOT EXISTS reviews (
    review_id INTEGER PRIMARY KEY AUTOINCREMENT,
    app_id INTEGER NOT NULL,
    platform_id INTEGER NOT NULL,
    source_review_id VARCHAR(255) NOT NULL,
    author_name VARCHAR(255) NOT NULL,
    title TEXT,
    content TEXT NOT NULL,
    rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
    app_version VARCHAR(50),
    review_date TIMESTAMP NOT NULL,
    thumbs_up_count INTEGER DEFAULT 0,
    developer_reply TEXT,
    developer_reply_date TIMESTAMP,
    ingested_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_duplicate BOOLEAN NOT NULL DEFAULT 0,
    sentiment_label VARCHAR(20),
    labeled_at TIMESTAMP,
    labeled_by VARCHAR(100),
    FOREIGN KEY (app_id) REFERENCES apps(app_id),
    FOREIGN KEY (platform_id) REFERENCES platforms(platform_id),
    UNIQUE (platform_id, source_review_id)
);

CREATE INDEX IF NOT EXISTS idx_reviews_platform ON reviews(platform_id);
CREATE INDEX IF NOT EXISTS idx_reviews_app ON reviews(app_id);
CREATE INDEX IF NOT EXISTS idx_reviews_rating ON reviews(rating);
CREATE INDEX IF NOT EXISTS idx_reviews_date ON reviews(review_date);
CREATE INDEX IF NOT EXISTS idx_reviews_ingested ON reviews(ingested_at);
CREATE INDEX IF NOT EXISTS idx_reviews_sentiment ON reviews(sentiment_label);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    status VARCHAR(20) NOT NULL DEFAULT 'running',
    reviews_fetched INTEGER DEFAULT 0,
    reviews_inserted INTEGER DEFAULT 0,
    reviews_skipped INTEGER DEFAULT 0,
    errors INTEGER DEFAULT 0,
    error_message TEXT,
    CONSTRAINT valid_status CHECK (status IN ('running', 'success', 'failed', 'warning'))
);