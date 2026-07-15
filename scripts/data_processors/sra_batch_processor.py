#!/usr/bin/env python3
"""
SRA Batch Processor - Automated pipeline for 5000 samples
Uses fetch_sra_metadata.py to find samples, then runs Nextflow pipeline
"""

import os
import sys
import json
import time
import psycopg2
import subprocess
import logging
from datetime import datetime
from typing import Optional, Dict, List, Tuple
from pathlib import Path

# Setup logging
import os
log_dir = '/tmp/logs'
os.makedirs(log_dir, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'{log_dir}/sra_batch_processor.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class SRABatchProcessor:
    """Automated processor for SRA samples with geo-coordinates"""
    
    def __init__(self):
        self.db_config = {
            'host': os.getenv('POSTGRES_HOST', 'postgres'),
            'port': os.getenv('POSTGRES_PORT', '5432'),
            'database': os.getenv('POSTGRES_DB', 'upgrade_db'),
            'user': os.getenv('POSTGRES_USER', 'upgrade'),
            'password': os.getenv('POSTGRES_PASSWORD')
        }
        
        self.data_dir = Path("/data")
        self.results_dir = Path("/results")
        self.nextflow_script = Path("/nextflow/main.nf")
        self.metadata_file = Path("/tmp/sra_metadata.json")
        
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
                        file_size_mb FLOAT,
                        country VARCHAR(100),
                        collection_date VARCHAR(50),
                        library_strategy VARCHAR(100),
                        platform VARCHAR(100),
                        instrument VARCHAR(100),
                        organism VARCHAR(200),
                        geo_loc_name VARCHAR(200),
                        
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
                        full_metadata JSONB,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                    
                    CREATE INDEX IF NOT EXISTS idx_sample_queue_status 
                        ON sample_queue(status);
                    CREATE INDEX IF NOT EXISTS idx_sample_queue_file_size 
                        ON sample_queue(file_size_mb);
                    CREATE INDEX IF NOT EXISTS idx_sample_queue_location 
                        ON sample_queue(latitude, longitude);
                """)
                conn.commit()
                logger.info("Sample queue table created/verified")
        finally:
            conn.close()
    
    def discover_samples_from_sra(self, limit: int = 5000, max_size_mb: float = None) -> int:
        """
        Use fetch_sra_metadata.py to discover samples
        Returns count of discovered samples
        """
        logger.info(f"Discovering up to {limit} samples from NCBI SRA...")
        
        # Build command for fetch_sra_metadata.py
        cmd = [
            'python3', '/scripts/fetch_sra_metadata.py',
            '--max-results', str(limit),
            '--has-coords',  # Only samples with coordinates
            '--worldwide',   # Search globally (not just Europe)
            '--output', str(self.metadata_file)
        ]
        
        if max_size_mb:
            cmd.extend(['--max-size', str(max_size_mb)])
        
        try:
            logger.info(f"Running: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode != 0:
                logger.error(f"fetch_sra_metadata failed: {result.stderr}")
                return 0
            
            logger.info(result.stdout)
            
            # Load metadata file
            if not self.metadata_file.exists():
                logger.error("Metadata file not created")
                return 0
            
            with open(self.metadata_file, 'r') as f:
                data = json.load(f)
            
            samples = data.get('samples', [])
            logger.info(f"Loaded {len(samples)} samples from metadata file")
            
            # Insert into database
            conn = self._get_db_connection()
            inserted = 0
            
            try:
                with conn.cursor() as cur:
                    for sample in samples:
                        try:
                            # Skip samples without valid coordinates
                            lat = sample.get('lat', 'N/A')
                            lon = sample.get('lon', 'N/A')
                            
                            if lat == 'N/A' or lon == 'N/A':
                                continue
                            
                            # Convert coordinates to float
                            try:
                                lat_float = float(lat)
                                lon_float = float(lon)
                            except (ValueError, TypeError):
                                logger.warning(f"Invalid coordinates for {sample['run_id']}: {lat}, {lon}")
                                continue
                            
                            cur.execute("""
                                INSERT INTO sample_queue 
                                (accession, latitude, longitude, file_size_mb, country, 
                                 collection_date, library_strategy, platform, instrument,
                                 organism, geo_loc_name, status, full_metadata)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending', %s)
                                ON CONFLICT (accession) DO NOTHING
                            """, (
                                sample['run_id'],
                                lat_float,
                                lon_float,
                                sample.get('file_size_mb', 0),
                                sample.get('country', 'Unknown'),
                                sample.get('collection_date', 'Unknown'),
                                sample.get('strategy', 'METAGENOMIC'),
                                sample.get('platform', 'Unknown'),
                                sample.get('instrument', 'Unknown'),
                                sample.get('organism', 'metagenome'),
                                sample.get('geo_loc_name', 'Unknown'),
                                json.dumps(sample)
                            ))
                            inserted += 1
                        except Exception as e:
                            logger.warning(f"Failed to insert {sample.get('run_id')}: {e}")
                            continue
                    
                    conn.commit()
                    logger.info(f"Inserted {inserted} samples into queue")
            finally:
                conn.close()
            
            return inserted
            
        except subprocess.TimeoutExpired:
            logger.error("Sample discovery timeout")
            return 0
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
            
            logger.info(f"Running: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=3600  # 1 hour timeout
            )
            
            if result.returncode != 0:
                error = f"fasterq-dump failed: {result.stderr[:500]}"
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
            
            logger.info(f"Downloaded {accession}: {len(fastq_files)} files, {sum(f.stat().st_size for f in fastq_files)/1024/1024:.1f} MB")
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
            
            # Run Nextflow with proper environment
            cmd = [
                'bash', '-c',
                f'export NXF_HOME=/tmp/nextflow-home && '
                f'cd /tmp && '
                f'nextflow run {self.nextflow_script} '
                f'--input_dir {input_dir} '
                f'--outdir {output_dir} '
                f'-work-dir /tmp/nextflow-work '
                f'-profile docker '
                f'-resume'
            ]
            
            logger.info(f"Running Nextflow for {accession}...")
            
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
                # Try to find any summary file
                summary_files = list((output_dir / "00_summary").glob("*_summary.json"))
                if summary_files:
                    summary_json = summary_files[0]
                    logger.info(f"Found summary: {summary_json.name}")
                else:
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
                           summary_json_path, geo_loc_name, organism
                    FROM sample_queue
                    WHERE accession = %s
                """, (accession,))
                row = cur.fetchone()
                
                if not row:
                    return False, "Sample not found in queue"
                
                lat, lon, country, collection_date, summary_path, geo_loc_name, organism = row
            
            # Read summary JSON
            if not Path(summary_path).exists():
                return False, f"Summary file not found: {summary_path}"
            
            with open(summary_path, 'r') as f:
                summary = json.load(f)
            
            quality_score = summary.get('quality_score', 0)
            amr_risk_score = summary.get('amr_risk_score', 0)
            
            # Get or create location
            with conn.cursor() as cur:
                # Try to find existing location near these coordinates
                cur.execute("""
                    SELECT location_id FROM locations
                    WHERE ABS(latitude - %s) < 0.01 
                      AND ABS(longitude - %s) < 0.01
                    LIMIT 1
                """, (lat, lon))
                
                location_row = cur.fetchone()
                
                if location_row:
                    location_id = location_row[0]
                    logger.info(f"Using existing location {location_id}")
                else:
                    # Create new location
                    location_name = geo_loc_name if geo_loc_name and geo_loc_name != 'Unknown' else f"SRA_{accession}"
                    
                    cur.execute("""
                        INSERT INTO locations 
                        (location_name, country, latitude, longitude, is_active, metadata)
                        VALUES (%s, %s, %s, %s, true, %s)
                        RETURNING location_id
                    """, (
                        location_name[:255],
                        country[:100] if country else 'Unknown',
                        lat,
                        lon,
                        json.dumps({'source': 'SRA', 'accession': accession})
                    ))
                    location_id = cur.fetchone()[0]
                    logger.info(f"Created location {location_id} for {accession}")
            
            # Insert sample
            with conn.cursor() as cur:
                # Parse collection date
                coll_date = None
                if collection_date and collection_date != 'Unknown':
                    try:
                        # Try various date formats
                        for fmt in ['%Y-%m-%d', '%Y/%m/%d', '%Y-%m', '%Y']:
                            try:
                                coll_date = datetime.strptime(collection_date.split()[0], fmt).date()
                                break
                            except:
                                continue
                    except:
                        pass
                
                cur.execute("""
                    INSERT INTO samples
                    (sample_id_original, location_id, sample_type, 
                     collection_date, sequencing_platform, quality_score, 
                     status, metadata)
                    VALUES (%s, %s, 'environmental', %s, 'NANOPORE', 
                            %s, 'analyzed', %s)
                    RETURNING sample_id
                """, (
                    accession,
                    location_id,
                    coll_date,
                    quality_score,
                    json.dumps({
                        **summary,
                        'organism': organism,
                        'geo_loc_name': geo_loc_name,
                        'source': 'NCBI_SRA'
                    })
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
            
            logger.info(f"✅ Posted {accession} to GeoDashboard (sample_id={sample_id}, quality={quality_score:.1f})")
            return True, None
            
        except Exception as e:
            error = f"GeoDashboard posting error: {str(e)}"
            logger.error(error)
            if conn:
                conn.close()
            return False, error
    
    def process_one_sample(self, accession: str) -> bool:
        """
        Complete pipeline for one sample: download -> process -> post
        Returns success status
        """
        logger.info(f"\n{'='*80}")
        logger.info(f"Processing {accession}")
        logger.info(f"{'='*80}")
        
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
    
    def run_batch_processing(self, max_samples: int = 5000, max_size_mb: float = None):
        """
        Main batch processing loop - processes samples sequentially
        """
        logger.info(f"\n{'='*80}")
        logger.info(f"SRA Batch Processor - Starting")
        logger.info(f"Max samples: {max_samples}")
        if max_size_mb:
            logger.info(f"Max file size: {max_size_mb} MB")
        logger.info(f"{'='*80}\n")
        
        self._create_sample_queue_table()
        
        conn = self._get_db_connection()
        
        try:
            # Get pending samples ordered by file size (smallest first)
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT accession, file_size_mb, geo_loc_name
                    FROM sample_queue
                    WHERE status = 'pending'
                    ORDER BY file_size_mb ASC
                    LIMIT %s
                """, (max_samples,))
                
                pending_samples = cur.fetchall()
            
            logger.info(f"Found {len(pending_samples)} pending samples in queue")
            
            if not pending_samples:
                logger.info("No pending samples. Discovering new samples from NCBI SRA...")
                discovered = self.discover_samples_from_sra(
                    limit=max_samples,
                    max_size_mb=max_size_mb
                )
                
                if discovered == 0:
                    logger.error("No samples discovered from SRA")
                    return
                
                # Re-query pending samples
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT accession, file_size_mb, geo_loc_name
                        FROM sample_queue
                        WHERE status = 'pending'
                        ORDER BY file_size_mb ASC
                        LIMIT %s
                    """, (max_samples,))
                    pending_samples = cur.fetchall()
            
            # Process samples one by one
            processed = 0
            failed = 0
            start_time = time.time()
            
            for accession, file_size, location in pending_samples:
                logger.info(f"\n--- Sample {processed + failed + 1}/{len(pending_samples)} ---")
                logger.info(f"Accession: {accession}")
                logger.info(f"Size: {file_size:.2f} MB")
                logger.info(f"Location: {location}")
                
                sample_start = time.time()
                success = self.process_one_sample(accession)
                sample_duration = time.time() - sample_start
                
                if success:
                    processed += 1
                    logger.info(f"✅ Completed in {sample_duration/60:.1f} minutes")
                else:
                    failed += 1
                    logger.info(f"❌ Failed after {sample_duration/60:.1f} minutes")
                
                # Calculate ETA
                total_duration = time.time() - start_time
                avg_time = total_duration / (processed + failed)
                remaining = len(pending_samples) - (processed + failed)
                eta_seconds = avg_time * remaining
                
                logger.info(f"\nProgress: {processed} completed, {failed} failed, {remaining} remaining")
                logger.info(f"Avg time per sample: {avg_time/60:.1f} minutes")
                logger.info(f"ETA: {eta_seconds/3600:.1f} hours")
                
                # Small delay between samples
                time.sleep(5)
            
            total_duration = time.time() - start_time
            
            logger.info(f"\n{'='*80}")
            logger.info(f"Batch Processing Complete")
            logger.info(f"{'='*80}")
            logger.info(f"Total time: {total_duration/3600:.2f} hours")
            logger.info(f"Samples processed: {processed}")
            logger.info(f"Samples failed: {failed}")
            logger.info(f"Success rate: {processed/(processed+failed)*100:.1f}%")
            logger.info(f"Avg time per sample: {total_duration/(processed+failed)/60:.1f} minutes")
            
        finally:
            conn.close()

def main():
    """Main entry point"""
    
    processor = SRABatchProcessor()
    
    # Get parameters from command line
    max_samples = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    max_size_mb = float(sys.argv[2]) if len(sys.argv) > 2 else None
    
    try:
        processor.run_batch_processing(
            max_samples=max_samples,
            max_size_mb=max_size_mb
        )
    except KeyboardInterrupt:
        logger.info("\n\nBatch processing interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
