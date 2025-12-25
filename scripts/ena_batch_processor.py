#!/usr/bin/env python3
"""
ENA Batch Processor - Automated pipeline for 5000 samples
Downloads samples with geo-coordinates, runs Nextflow pipeline, posts to GeoDashboard
"""

import os
import sys
import json
import time
import psycopg2
import requests
import subprocess
import logging
from datetime import datetime
from typing import Optional, Dict, List, Tuple
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/logs/ena_batch_processor.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class ENABatchProcessor:
    """Automated processor for ENA samples with geo-coordinates"""
    
    def __init__(self):
        self.db_config = {
            'host': os.getenv('POSTGRES_HOST', 'postgres'),
            'port': os.getenv('POSTGRES_PORT', '5432'),
            'database': os.getenv('POSTGRES_DB', 'upgrade_db'),
            'user': os.getenv('POSTGRES_USER', 'upgrade'),
            'password': os.getenv('POSTGRES_PASSWORD')
        }
        
        self.ena_portal_url = "https://www.ebi.ac.uk/ena/portal/api"
        self.data_dir = Path("/data")
        self.results_dir = Path("/results")
        self.nextflow_script = Path("/nextflow/main.nf")
        
    def _get_db_connection(self):
        """Create database connection"""
        try:
            conn = psycopg2.connect(**self.db_config)
            return conn
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            raise
    
    def _create_sample_queue_table(self):
        """Create table for sample processing queue"""
        conn = self._get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS sample_queue (
                        id SERIAL PRIMARY KEY,
                        accession VARCHAR(50) UNIQUE NOT NULL,
                        latitude FLOAT,
                        longitude FLOAT,
                        file_size BIGINT,
                        country VARCHAR(100),
                        collection_date DATE,
                        library_strategy VARCHAR(100),
                        platform VARCHAR(100),
                        
                        -- Processing status
                        status VARCHAR(20) DEFAULT 'pending',
                        -- Status: pending, downloading, processing, completed, failed, skipped
                        
                        -- Progress tracking
                        download_started_at TIMESTAMP,
                        download_completed_at TIMESTAMP,
                        pipeline_started_at TIMESTAMP,
                        pipeline_completed_at TIMESTAMP,
                        
                        -- Results
                        quality_score FLOAT,
                        amr_risk_score FLOAT,
                        summary_json_path TEXT,
                        
                        -- Error tracking
                        error_message TEXT,
                        retry_count INT DEFAULT 0,
                        last_attempt_at TIMESTAMP,
                        
                        -- Metadata
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                    
                    CREATE INDEX IF NOT EXISTS idx_sample_queue_status 
                        ON sample_queue(status);
                    CREATE INDEX IF NOT EXISTS idx_sample_queue_file_size 
                        ON sample_queue(file_size);
                    CREATE INDEX IF NOT EXISTS idx_sample_queue_location 
                        ON sample_queue(latitude, longitude);
                """)
                conn.commit()
                logger.info("Sample queue table created/verified")
        finally:
            conn.close()
    
    def discover_samples_from_ena(self, limit: int = 5000) -> int:
        """
        Query ENA API for samples with geo-coordinates
        Returns count of discovered samples
        """
        logger.info(f"Discovering up to {limit} samples from ENA...")
        
        # Query for metagenomic samples with coordinates
        # Sorted by smallest file size first
        query = 'library_strategy="METAGENOMIC" AND lat IS NOT NULL AND lon IS NOT NULL'
        
        params = {
            'result': 'read_run',
            'query': query,
            'format': 'json',
            'limit': limit,
            'fields': 'run_accession,lat,lon,fastq_bytes,country,collection_date,library_strategy,instrument_platform',
            'sortfields': 'fastq_bytes',  # Sort by file size ascending
            'sortdir': 'asc'
        }
        
        try:
            logger.info(f"Querying ENA API: {query}")
            response = requests.get(
                f"{self.ena_portal_url}/search",
                params=params,
                verify=False,
                timeout=60
            )
            
            if response.status_code != 200:
                logger.error(f"ENA API error: HTTP {response.status_code}")
                logger.error(f"Response: {response.text[:500]}")
                return 0
            
            samples = response.json()
            logger.info(f"Found {len(samples)} samples from ENA")
            
            # Insert into database
            conn = self._get_db_connection()
            inserted = 0
            
            try:
                with conn.cursor() as cur:
                    for sample in samples:
                        try:
                            cur.execute("""
                                INSERT INTO sample_queue 
                                (accession, latitude, longitude, file_size, country, 
                                 collection_date, library_strategy, platform, status)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'pending')
                                ON CONFLICT (accession) DO NOTHING
                            """, (
                                sample.get('run_accession'),
                                float(sample.get('lat', 0)),
                                float(sample.get('lon', 0)),
                                int(sample.get('fastq_bytes', 0)),
                                sample.get('country'),
                                sample.get('collection_date'),
                                sample.get('library_strategy'),
                                sample.get('instrument_platform')
                            ))
                            inserted += 1
                        except Exception as e:
                            logger.warning(f"Failed to insert {sample.get('run_accession')}: {e}")
                            continue
                    
                    conn.commit()
                    logger.info(f"Inserted {inserted} samples into queue")
            finally:
                conn.close()
            
            return inserted
            
        except Exception as e:
            logger.error(f"Sample discovery failed: {e}")
            return 0
    
    def download_sample(self, accession: str) -> Tuple[bool, Optional[str]]:
        """
        Download sample using fasterq-dump
        Returns (success, error_message)
        """
        logger.info(f"Downloading {accession}...")
        
        sample_dir = self.data_dir / accession / "raw"
        sample_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # Update status to downloading
            conn = self._get_db_connection()
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE sample_queue 
                    SET status = 'downloading',
                        download_started_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE accession = %s
                """, (accession,))
                conn.commit()
            conn.close()
            
            # Download using fasterq-dump
            cmd = [
                'fasterq-dump',
                accession,
                '--outdir', str(sample_dir),
                '--threads', '4',
                '--progress',
                '--split-files'
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=3600  # 1 hour timeout
            )
            
            if result.returncode != 0:
                error = f"fasterq-dump failed: {result.stderr}"
                logger.error(error)
                return False, error
            
            # Verify files downloaded
            fastq_files = list(sample_dir.glob("*.fastq*"))
            if not fastq_files:
                error = "No FASTQ files downloaded"
                logger.error(error)
                return False, error
            
            # Update status
            conn = self._get_db_connection()
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE sample_queue 
                    SET download_completed_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE accession = %s
                """, (accession,))
                conn.commit()
            conn.close()
            
            logger.info(f"Downloaded {accession}: {len(fastq_files)} files")
            return True, None
            
        except subprocess.TimeoutExpired:
            error = "Download timeout (>1 hour)"
            logger.error(error)
            return False, error
        except Exception as e:
            error = f"Download error: {str(e)}"
            logger.error(error)
            return False, error
    
    def run_nextflow_pipeline(self, accession: str) -> Tuple[bool, Optional[str]]:
        """
        Run Nextflow pipeline for sample
        Returns (success, error_message)
        """
        logger.info(f"Running pipeline for {accession}...")
        
        input_dir = self.data_dir / accession / "raw"
        output_dir = self.results_dir / accession
        
        try:
            # Update status
            conn = self._get_db_connection()
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE sample_queue 
                    SET status = 'processing',
                        pipeline_started_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE accession = %s
                """, (accession,))
                conn.commit()
            conn.close()
            
            # Run Nextflow
            cmd = [
                'nextflow', 'run', str(self.nextflow_script),
                '--input_dir', str(input_dir),
                '--outdir', str(output_dir),
                '-profile', 'docker',
                '-resume'
            ]
            
            logger.info(f"Nextflow command: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=7200  # 2 hour timeout
            )
            
            if result.returncode != 0:
                error = f"Nextflow failed: {result.stderr[:500]}"
                logger.error(error)
                return False, error
            
            # Verify summary JSON was created
            summary_json = output_dir / "00_summary" / f"{accession}_summary.json"
            if not summary_json.exists():
                error = "Summary JSON not created"
                logger.error(error)
                return False, error
            
            # Update status
            conn = self._get_db_connection()
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE sample_queue 
                    SET pipeline_completed_at = CURRENT_TIMESTAMP,
                        summary_json_path = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE accession = %s
                """, (str(summary_json), accession))
                conn.commit()
            conn.close()
            
            logger.info(f"Pipeline completed for {accession}")
            return True, None
            
        except subprocess.TimeoutExpired:
            error = "Pipeline timeout (>2 hours)"
            logger.error(error)
            return False, error
        except Exception as e:
            error = f"Pipeline error: {str(e)}"
            logger.error(error)
            return False, error
    
    def post_to_geodashboard(self, accession: str) -> Tuple[bool, Optional[str]]:
        """
        Parse results and insert into database for GeoDashboard
        Returns (success, error_message)
        """
        logger.info(f"Posting {accession} to GeoDashboard...")
        
        try:
            conn = self._get_db_connection()
            
            # Get sample metadata from queue
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT latitude, longitude, country, collection_date, 
                           summary_json_path
                    FROM sample_queue
                    WHERE accession = %s
                """, (accession,))
                row = cur.fetchone()
                
                if not row:
                    return False, "Sample not found in queue"
                
                lat, lon, country, collection_date, summary_path = row
            
            # Read summary JSON
            with open(summary_path, 'r') as f:
                summary = json.load(f)
            
            quality_score = summary.get('quality_score', 0)
            amr_risk_score = summary.get('amr_risk_score', 0)
            
            # Get or create location
            with conn.cursor() as cur:
                # Try to find existing location near these coordinates
                cur.execute("""
                    SELECT location_id FROM locations
                    WHERE ABS(latitude - %s) < 0.1 
                      AND ABS(longitude - %s) < 0.1
                    LIMIT 1
                """, (lat, lon))
                
                location_row = cur.fetchone()
                
                if location_row:
                    location_id = location_row[0]
                else:
                    # Create new location
                    cur.execute("""
                        INSERT INTO locations 
                        (location_name, country, latitude, longitude, is_active)
                        VALUES (%s, %s, %s, %s, true)
                        RETURNING location_id
                    """, (f"ENA_{accession}", country or 'Unknown', lat, lon))
                    location_id = cur.fetchone()[0]
                    logger.info(f"Created location {location_id} for {accession}")
            
            # Insert sample
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO samples
                    (sample_id_original, location_id, sample_type, 
                     collection_date, sequencing_platform, quality_score, 
                     status, metadata)
                    VALUES (%s, %s, 'environmental', %s, 'OXFORD_NANOPORE', 
                            %s, 'analyzed', %s)
                    RETURNING sample_id
                """, (
                    accession,
                    location_id,
                    collection_date,
                    quality_score,
                    json.dumps(summary)
                ))
                sample_id = cur.fetchone()[0]
                logger.info(f"Created sample {sample_id} for {accession}")
            
            # Update queue with quality scores
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE sample_queue
                    SET status = 'completed',
                        quality_score = %s,
                        amr_risk_score = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE accession = %s
                """, (quality_score, amr_risk_score, accession))
            
            conn.commit()
            conn.close()
            
            logger.info(f"Posted {accession} to GeoDashboard (sample_id={sample_id})")
            return True, None
            
        except Exception as e:
            error = f"GeoDashboard posting error: {str(e)}"
            logger.error(error)
            return False, error
    
    def process_one_sample(self, accession: str) -> bool:
        """
        Complete pipeline for one sample: download -> process -> post
        Returns success status
        """
        logger.info(f"=== Processing {accession} ===")
        
        conn = self._get_db_connection()
        
        try:
            # Step 1: Download
            success, error = self.download_sample(accession)
            if not success:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE sample_queue
                        SET status = 'failed',
                            error_message = %s,
                            retry_count = retry_count + 1,
                            last_attempt_at = CURRENT_TIMESTAMP,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE accession = %s
                    """, (error, accession))
                    conn.commit()
                return False
            
            # Step 2: Run pipeline
            success, error = self.run_nextflow_pipeline(accession)
            if not success:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE sample_queue
                        SET status = 'failed',
                            error_message = %s,
                            retry_count = retry_count + 1,
                            last_attempt_at = CURRENT_TIMESTAMP,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE accession = %s
                    """, (error, accession))
                    conn.commit()
                return False
            
            # Step 3: Post to GeoDashboard
            success, error = self.post_to_geodashboard(accession)
            if not success:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE sample_queue
                        SET status = 'failed',
                            error_message = %s,
                            retry_count = retry_count + 1,
                            last_attempt_at = CURRENT_TIMESTAMP,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE accession = %s
                    """, (error, accession))
                    conn.commit()
                return False
            
            logger.info(f"✅ Successfully processed {accession}")
            return True
            
        except Exception as e:
            logger.error(f"Unexpected error processing {accession}: {e}")
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE sample_queue
                    SET status = 'failed',
                        error_message = %s,
                        retry_count = retry_count + 1,
                        last_attempt_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE accession = %s
                """, (str(e), accession))
                conn.commit()
            return False
        finally:
            conn.close()
    
    def run_batch_processing(self, max_samples: int = 5000):
        """
        Main batch processing loop - processes samples sequentially
        """
        logger.info(f"=== Starting Batch Processing (max {max_samples} samples) ===")
        
        self._create_sample_queue_table()
        
        conn = self._get_db_connection()
        
        try:
            # Get pending samples ordered by file size (smallest first)
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT accession, file_size
                    FROM sample_queue
                    WHERE status = 'pending'
                    ORDER BY file_size ASC
                    LIMIT %s
                """, (max_samples,))
                
                pending_samples = cur.fetchall()
            
            logger.info(f"Found {len(pending_samples)} pending samples")
            
            if not pending_samples:
                logger.info("No pending samples. Discovering new samples from ENA...")
                discovered = self.discover_samples_from_ena(limit=max_samples)
                
                if discovered == 0:
                    logger.error("No samples discovered from ENA")
                    return
                
                # Re-query pending samples
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT accession, file_size
                        FROM sample_queue
                        WHERE status = 'pending'
                        ORDER BY file_size ASC
                        LIMIT %s
                    """, (max_samples,))
                    pending_samples = cur.fetchall()
            
            # Process samples one by one
            processed = 0
            failed = 0
            
            for accession, file_size in pending_samples:
                logger.info(f"\n--- Sample {processed + failed + 1}/{len(pending_samples)} ---")
                logger.info(f"Accession: {accession}, Size: {file_size / 1024 / 1024:.2f} MB")
                
                success = self.process_one_sample(accession)
                
                if success:
                    processed += 1
                else:
                    failed += 1
                
                logger.info(f"Progress: {processed} completed, {failed} failed")
                
                # Small delay between samples
                time.sleep(5)
            
            logger.info(f"\n=== Batch Processing Complete ===")
            logger.info(f"Total processed: {processed}")
            logger.info(f"Total failed: {failed}")
            logger.info(f"Success rate: {processed/(processed+failed)*100:.1f}%")
            
        finally:
            conn.close()

def main():
    """Main entry point"""
    
    # Check if running in container
    if not os.path.exists('/.dockerenv'):
        logger.warning("Not running in Docker container - some paths may not work")
    
    processor = ENABatchProcessor()
    
    # Get batch size from command line or use default
    max_samples = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    
    try:
        processor.run_batch_processing(max_samples=max_samples)
    except KeyboardInterrupt:
        logger.info("\nBatch processing interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
