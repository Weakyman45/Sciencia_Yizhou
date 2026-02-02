import sqlite3
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class RunMetrics:
    # Timing
    started_at: datetime = None
    completed_at: datetime = None
    fetch_start: datetime = None
    fetch_end: datetime = None
    transform_start: datetime = None
    transform_end: datetime = None
    load_start: datetime = None
    load_end: datetime = None
    
    # Fetch metrics
    reviews_fetched: int = 0
    reviews_fetched_google: int = 0
    reviews_fetched_apple: int = 0
    fetch_retries: int = 0
    fetch_failures: int = 0
    
    # Transform metrics
    reviews_transformed: int = 0
    duplicate_content_count: int = 0
    invalid_reviews: int = 0
    
    # Load metrics
    reviews_inserted: int = 0
    reviews_skipped: int = 0
    errors: int = 0
    
    # Data quality metrics
    missing_app_version_count: int = 0
    rating_distribution: Dict[int, int] = field(default_factory=lambda: {1: 0, 2: 0, 3: 0, 4: 0, 5: 0})
    
    # Config snapshot
    config_interval: str = ""
    config_google_target: int = 0
    config_apple_target: int = 0
    
    # Status
    status: str = "running"
    error_message: Optional[str] = None
    
    def get_fetch_duration(self) -> Optional[float]:
        if self.fetch_start and self.fetch_end:
            return (self.fetch_end - self.fetch_start).total_seconds()
        return None
    
    def get_transform_duration(self) -> Optional[float]:
        if self.transform_start and self.transform_end:
            return (self.transform_end - self.transform_start).total_seconds()
        return None
    
    def get_load_duration(self) -> Optional[float]:
        if self.load_start and self.load_end:
            return (self.load_end - self.load_start).total_seconds()
        return None
    
    def get_total_duration(self) -> Optional[float]:
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


class PipelineMonitor:
    """
    Monitors pipeline execution and tracks metrics.
    """
    
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.metrics = RunMetrics()
        self.run_id: Optional[int] = None
    
    def start_run(self, config: Dict[str, Any]) -> int:
        """Start tracking a new pipeline run."""
        self.metrics = RunMetrics()
        self.metrics.started_at = datetime.now(timezone.utc)
        
        # Capture config snapshot
        sources = config.get('sources', {})
        schedule = config.get('schedule', {})
        
        self.metrics.config_interval = schedule.get('frequency', 'daily')
        self.metrics.config_google_target = sources.get('google_play', {}).get('target_reviews', 0)
        self.metrics.config_apple_target = sources.get('apple_app_store', {}).get('target_reviews', 0)
        
        # Insert initial run record
        cursor = self.conn.execute(
            """
            INSERT INTO pipeline_runs (
                started_at, status, config_interval, 
                config_google_target, config_apple_target
            ) VALUES (?, 'running', ?, ?, ?)
            """,
            (
                self.metrics.started_at.isoformat(),
                self.metrics.config_interval,
                self.metrics.config_google_target,
                self.metrics.config_apple_target
            )
        )
        self.conn.commit()
        self.run_id = cursor.lastrowid
        
        logger.info(f"Started pipeline run #{self.run_id}")
        return self.run_id
    
    def start_fetch(self):
        """Mark the start of fetch phase."""
        self.metrics.fetch_start = datetime.now(timezone.utc)
    
    def end_fetch(self, google_count: int, apple_count: int, retries: int = 0, failures: int = 0):
        """Mark the end of fetch phase with results."""
        self.metrics.fetch_end = datetime.now(timezone.utc)
        self.metrics.reviews_fetched_google = google_count
        self.metrics.reviews_fetched_apple = apple_count
        self.metrics.reviews_fetched = google_count + apple_count
        self.metrics.fetch_retries = retries
        self.metrics.fetch_failures = failures
    
    def start_transform(self):
        """Mark the start of transform phase."""
        self.metrics.transform_start = datetime.now(timezone.utc)
    
    def end_transform(self, transformed: int, duplicates: int, invalid: int, 
                      missing_version: int, rating_dist: Dict[int, int]):
        """Mark the end of transform phase with results."""
        self.metrics.transform_end = datetime.now(timezone.utc)
        self.metrics.reviews_transformed = transformed
        self.metrics.duplicate_content_count = duplicates
        self.metrics.invalid_reviews = invalid
        self.metrics.missing_app_version_count = missing_version
        self.metrics.rating_distribution = rating_dist
    
    def start_load(self):
        """Mark the start of load phase."""
        self.metrics.load_start = datetime.now(timezone.utc)
    
    def end_load(self, inserted: int, skipped: int, errors: int):
        """Mark the end of load phase with results."""
        self.metrics.load_end = datetime.now(timezone.utc)
        self.metrics.reviews_inserted = inserted
        self.metrics.reviews_skipped = skipped
        self.metrics.errors = errors
    
    def complete_run(self, status: str = 'success', error_message: Optional[str] = None):
        """Complete the run and save all metrics."""
        self.metrics.completed_at = datetime.now(timezone.utc)
        self.metrics.status = status
        self.metrics.error_message = error_message
        
        # Update the run record with all metrics
        self.conn.execute(
            """
            UPDATE pipeline_runs SET
                completed_at = ?,
                status = ?,
                reviews_fetched = ?,
                reviews_fetched_google = ?,
                reviews_fetched_apple = ?,
                reviews_inserted = ?,
                reviews_skipped = ?,
                errors = ?,
                fetch_duration_seconds = ?,
                transform_duration_seconds = ?,
                load_duration_seconds = ?,
                total_duration_seconds = ?,
                duplicate_content_count = ?,
                missing_app_version_count = ?,
                rating_1_count = ?,
                rating_2_count = ?,
                rating_3_count = ?,
                rating_4_count = ?,
                rating_5_count = ?,
                fetch_retries = ?,
                fetch_failures = ?,
                error_message = ?
            WHERE run_id = ?
            """,
            (
                self.metrics.completed_at.isoformat(),
                status,
                self.metrics.reviews_fetched,
                self.metrics.reviews_fetched_google,
                self.metrics.reviews_fetched_apple,
                self.metrics.reviews_inserted,
                self.metrics.reviews_skipped,
                self.metrics.errors,
                self.metrics.get_fetch_duration(),
                self.metrics.get_transform_duration(),
                self.metrics.get_load_duration(),
                self.metrics.get_total_duration(),
                self.metrics.duplicate_content_count,
                self.metrics.missing_app_version_count,
                self.metrics.rating_distribution.get(1, 0),
                self.metrics.rating_distribution.get(2, 0),
                self.metrics.rating_distribution.get(3, 0),
                self.metrics.rating_distribution.get(4, 0),
                self.metrics.rating_distribution.get(5, 0),
                self.metrics.fetch_retries,
                self.metrics.fetch_failures,
                error_message,
                self.run_id
            )
        )
        self.conn.commit()
        
        # Check for anomalies
        self._check_anomalies()
        
        logger.info(f"Completed pipeline run #{self.run_id} with status: {status}")
    
    def _check_anomalies(self):
        """Check for anomalies compared to recent runs."""
        # Get last 5 successful runs (excluding current)
        cursor = self.conn.execute(
            """
            SELECT run_id, reviews_inserted, total_duration_seconds,
                   rating_1_count, rating_2_count, rating_3_count, 
                   rating_4_count, rating_5_count
            FROM pipeline_runs
            WHERE status = 'success' AND run_id != ?
            ORDER BY run_id DESC
            LIMIT 5
            """,
            (self.run_id,)
        )
        recent_runs = cursor.fetchall()
        
        if not recent_runs:
            return  # No historical data to compare
        
        # Calculate averages from recent runs
        avg_inserted = sum(r[1] or 0 for r in recent_runs) / len(recent_runs)
        avg_duration = sum(r[2] or 0 for r in recent_runs) / len(recent_runs)
        
        # Check for significant drop in new records (>50% drop)
        if avg_inserted > 0 and self.metrics.reviews_inserted < avg_inserted * 0.5:
            self._create_alert(
                'rate_drop',
                'warning',
                f"New records dropped significantly: {self.metrics.reviews_inserted} vs avg {avg_inserted:.0f}",
                'reviews_inserted',
                self.metrics.reviews_inserted,
                avg_inserted * 0.5
            )
        
        # Check for duration spike (>2x average)
        total_duration = self.metrics.get_total_duration() or 0
        if avg_duration > 0 and total_duration > avg_duration * 2:
            self._create_alert(
                'duration_spike',
                'warning',
                f"Run duration spiked: {total_duration:.1f}s vs avg {avg_duration:.1f}s",
                'total_duration_seconds',
                total_duration,
                avg_duration * 2
            )
        
        # Check for high error rate
        if self.metrics.reviews_fetched > 0:
            error_rate = self.metrics.errors / self.metrics.reviews_fetched
            if error_rate > 0.05:  # >5% error rate
                self._create_alert(
                    'high_error_rate',
                    'warning',
                    f"High error rate: {error_rate:.1%}",
                    'error_rate',
                    error_rate,
                    0.05
                )
        
        # Check for rating distribution shift
        self._check_rating_drift(recent_runs)
    
    def _check_rating_drift(self, recent_runs: List):
        if not recent_runs or self.metrics.reviews_fetched == 0:
            return
        
        # Calculate average rating distribution from recent runs
        total_reviews_recent = 0
        avg_dist = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        
        for run in recent_runs:
            run_total = sum(run[3:8])  # rating counts
            if run_total > 0:
                total_reviews_recent += run_total
                for i, rating in enumerate(range(1, 6)):
                    avg_dist[rating] += run[3 + i]
        
        if total_reviews_recent == 0:
            return
        
        # Normalize to percentages
        for rating in avg_dist:
            avg_dist[rating] /= total_reviews_recent
        
        # Calculate current distribution percentages
        current_total = sum(self.metrics.rating_distribution.values())
        if current_total == 0:
            return
        
        current_dist = {k: v / current_total for k, v in self.metrics.rating_distribution.items()}
        
        # Check for significant drift (>10 percentage points)
        for rating in range(1, 6):
            diff = abs(current_dist.get(rating, 0) - avg_dist.get(rating, 0))
            if diff > 0.10:
                self._create_alert(
                    'rating_drift',
                    'info',
                    f"Rating {rating} distribution shifted: {current_dist[rating]:.1%} vs avg {avg_dist[rating]:.1%}",
                    f'rating_{rating}_pct',
                    current_dist[rating],
                    avg_dist[rating]
                )
    
    def _create_alert(self, alert_type: str, severity: str, message: str,
                      metric_name: str, metric_value: float, threshold_value: float):
        """Create a monitoring alert."""
        self.conn.execute(
            """
            INSERT INTO monitoring_alerts (
                run_id, alert_type, severity, message,
                metric_name, metric_value, threshold_value
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (self.run_id, alert_type, severity, message,
             metric_name, metric_value, threshold_value)
        )
        self.conn.commit()
        
        logger.warning(f"ALERT [{severity.upper()}] {alert_type}: {message}")


def get_run_comparison(conn: sqlite3.Connection, num_runs: int = 10) -> List[Dict]:
    """Get metrics from recent runs for comparison."""
    cursor = conn.execute(
        """
        SELECT 
            run_id,
            started_at,
            status,
            reviews_fetched,
            reviews_inserted,
            reviews_skipped,
            total_duration_seconds,
            fetch_retries,
            errors
        FROM pipeline_runs
        ORDER BY run_id DESC
        LIMIT ?
        """,
        (num_runs,)
    )
    
    columns = ['run_id', 'started_at', 'status', 'fetched', 'inserted', 
               'skipped', 'duration_sec', 'retries', 'errors']
    
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def get_recent_alerts(conn: sqlite3.Connection, num_alerts: int = 20) -> List[Dict]:
    """Get recent monitoring alerts."""
    cursor = conn.execute(
        """
        SELECT 
            a.alert_id,
            a.run_id,
            a.alert_type,
            a.severity,
            a.message,
            a.created_at
        FROM monitoring_alerts a
        ORDER BY a.created_at DESC
        LIMIT ?
        """,
        (num_alerts,)
    )
    
    columns = ['alert_id', 'run_id', 'type', 'severity', 'message', 'created_at']
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def generate_monitoring_report(conn: sqlite3.Connection) -> str:
    """Generate a text-based monitoring report."""
    report_lines = []
    report_lines.append("=" * 70)
    report_lines.append("PIPELINE MONITORING REPORT")
    report_lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    report_lines.append("=" * 70)
    
    # Recent runs summary
    report_lines.append("\n## RECENT RUNS (Last 10)")
    report_lines.append("-" * 70)
    
    runs = get_run_comparison(conn, 10)
    if runs:
        report_lines.append(f"{'Run':<6} {'Status':<10} {'Fetched':<10} {'Inserted':<10} {'Duration':<12} {'Errors':<8}")
        report_lines.append("-" * 70)
        for run in runs:
            duration = f"{run['duration_sec']:.1f}s" if run['duration_sec'] else "N/A"
            report_lines.append(
                f"#{run['run_id']:<5} {run['status']:<10} {run['fetched']:<10} "
                f"{run['inserted']:<10} {duration:<12} {run['errors']:<8}"
            )
    else:
        report_lines.append("No runs recorded yet.")
    
    # Alerts summary
    report_lines.append("\n## RECENT ALERTS")
    report_lines.append("-" * 70)
    
    alerts = get_recent_alerts(conn, 10)
    if alerts:
        for alert in alerts:
            report_lines.append(
                f"[{alert['severity'].upper()}] Run #{alert['run_id']} - "
                f"{alert['type']}: {alert['message']}"
            )
    else:
        report_lines.append("No alerts recorded.")
    
    # Database stats
    report_lines.append("\n## DATABASE STATS")
    report_lines.append("-" * 70)
    
    cursor = conn.execute("SELECT COUNT(*) FROM reviews")
    total_reviews = cursor.fetchone()[0]
    
    cursor = conn.execute("""
        SELECT p.display_name, COUNT(r.review_id)
        FROM reviews r
        JOIN platforms p ON r.platform_id = p.platform_id
        GROUP BY p.platform_id
    """)
    platform_counts = cursor.fetchall()
    
    report_lines.append(f"Total reviews: {total_reviews:,}")
    for platform, count in platform_counts:
        report_lines.append(f"  - {platform}: {count:,}")
    
    report_lines.append("\n" + "=" * 70)
    
    return "\n".join(report_lines)