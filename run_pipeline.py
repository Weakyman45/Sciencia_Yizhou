#!/usr/bin/env python3
import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from pipeline.fetch import fetch_all
from pipeline.transform import transform_reviews
from pipeline.load import load_reviews
from pipeline.database import (
    get_connection, 
    init_schema, 
    get_review_count,
    start_pipeline_run,
    complete_pipeline_run
)


def setup_logging(config: dict) -> logging.Logger:
    """Configure logging based on config settings."""
    log_config = config.get('logging', {})
    log_level = getattr(logging, log_config.get('level', 'INFO').upper())
    log_file = log_config.get('file', 'logs/pipeline.log')
    
    # Ensure log directory exists
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)
    
    # Configure logging
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s %(levelname)-5s %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    return logging.getLogger(__name__)


def load_config(config_path: str) -> dict:
    """Load configuration from YAML file."""
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def run_pipeline(
    config: dict, 
    dry_run: bool = False,
    google_only: bool = False,
    apple_only: bool = False
) -> dict:
    logger = logging.getLogger(__name__)
    
    results = {
        'status': 'success',
        'started_at': datetime.now(timezone.utc).isoformat(),
        'fetched': 0,
        'transformed': 0,
        'inserted': 0,
        'skipped': 0,
        'errors': 0,
        'error_message': None
    }
    
    # Modify config based on flags
    if google_only:
        config['sources']['apple_app_store']['enabled'] = False
        logger.info("Running Google Play only (--google-only)")
    if apple_only:
        config['sources']['google_play']['enabled'] = False
        logger.info("Running Apple App Store only (--apple-only)")
    
    db_config = config.get('database', {})
    db_path = db_config.get('path', 'data/reviews.db')
    schema_file = db_config.get('schema_file', 'schema.sql')
    
    conn = None
    run_id = None
    
    try:
        logger.info("=" * 60)
        logger.info("Data Ingestion Pipeline Started")
        logger.info("=" * 60)
        
        if not dry_run:
            # Ensure data directory exists
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            
            conn = get_connection(db_path)
            init_schema(conn, schema_file)
            run_id = start_pipeline_run(conn)
            
            before_count = get_review_count(conn)
            logger.info(f"Database initialized. Current review count: {before_count}")
        
        # Step 1: Fetch
        logger.info("-" * 60)
        logger.info("STEP 1: Fetching reviews")
        logger.info("-" * 60)
        
        raw_data = fetch_all(config)
        
        total_fetched = (
            len(raw_data.get('google_play', [])) + 
            len(raw_data.get('apple_app_store', []))
        )
        results['fetched'] = total_fetched
        
        logger.info(f"Fetch complete: {total_fetched} total reviews")
        logger.info(f"  - Google Play: {len(raw_data.get('google_play', []))}")
        logger.info(f"  - Apple App Store: {len(raw_data.get('apple_app_store', []))}")
        
        if total_fetched == 0:
            logger.warning("No reviews fetched. Check configuration and network.")
            results['status'] = 'warning'
            return results
        
        # Step 2: Transform
        logger.info("-" * 60)
        logger.info("STEP 2: Transforming reviews")
        logger.info("-" * 60)
        
        normalized_reviews = transform_reviews(raw_data)
        results['transformed'] = len(normalized_reviews)
        
        logger.info(f"Transform complete: {len(normalized_reviews)} valid reviews")
             
        # Step 3: Load
        if dry_run:
            logger.info("-" * 60)
            logger.info("STEP 3: Load (SKIPPED - dry run mode)")
            logger.info("-" * 60)
            logger.info(f"Would have loaded {len(normalized_reviews)} reviews")
        else:
            logger.info("-" * 60)
            logger.info("STEP 3: Loading to database")
            logger.info("-" * 60)
            
            batch_size = config.get('pipeline', {}).get('batch_size', 100)
            load_stats = load_reviews(conn, normalized_reviews, batch_size)
            
            results['inserted'] = load_stats['inserted']
            results['skipped'] = load_stats['skipped']
            results['errors'] = load_stats['errors']
            
            after_count = get_review_count(conn)
            logger.info(f"Database now contains {after_count} reviews (+{after_count - before_count})")

        results['completed_at'] = datetime.now(timezone.utc).isoformat()
        
        logger.info("=" * 60)
        logger.info("Pipeline Completed Successfully")
        logger.info("=" * 60)
        logger.info(f"  Fetched:     {results['fetched']:,}")
        logger.info(f"  Transformed: {results['transformed']:,}")
        logger.info(f"  Inserted:    {results['inserted']:,}")
        logger.info(f"  Skipped:     {results['skipped']:,}")
        logger.info(f"  Errors:      {results['errors']:,}")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        results['status'] = 'failed'
        results['error_message'] = str(e)
        
    finally:
        # Record pipeline run in database
        if conn and run_id:
            complete_pipeline_run(
                conn,
                run_id,
                results['status'],
                results['fetched'],
                results['inserted'],
                results['skipped'],
                results['errors'],
                results.get('error_message')
            )
            conn.close()
    
    return results


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Run the data ingestion pipeline',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
    Examples:
  python run_pipeline.py                    # Full pipeline run
  python run_pipeline.py --dry-run          # Test without loading to DB
  python run_pipeline.py --google-only      # Only fetch Google Play
  python run_pipeline.py --apple-only       # Only fetch Apple App Store
        """
    )
    parser.add_argument(
        '--config', '-c',
        default='config.yaml',
        help='Path to configuration file (default: config.yaml)'
    )
    parser.add_argument(
        '--dry-run', '-n',
        action='store_true',
        help='Fetch and transform only, do not load to database'
    )
    parser.add_argument(
        '--google-only',
        action='store_true',
        help='Only fetch from Google Play'
    )
    parser.add_argument(
        '--apple-only',
        action='store_true',
        help='Only fetch from Apple App Store'
    )
    
    args = parser.parse_args()
    
    # Validate flags
    if args.google_only and args.apple_only:
        print("Error: Cannot specify both --google-only and --apple-only")
        sys.exit(1)
    
    # Load config
    try:
        config = load_config(args.config)
    except FileNotFoundError:
        print(f"Error: Configuration file not found: {args.config}")
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"Error: Invalid YAML in configuration file: {e}")
        sys.exit(1)
    
    # Setup logging
    setup_logging(config)
    
    # Run pipeline
    results = run_pipeline(
        config, 
        dry_run=args.dry_run,
        google_only=args.google_only,
        apple_only=args.apple_only
    )
    
    # Exit with appropriate code
    if results['status'] == 'failed':
        sys.exit(1)
    sys.exit(0)


if __name__ == '__main__':
    main()