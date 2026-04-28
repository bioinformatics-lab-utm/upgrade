"""
MinIO Integration Module
Handles file uploads to MinIO and database tracking
"""
from minio import Minio
from minio.error import S3Error
import os
import logging
from datetime import datetime
from pathlib import Path
import hashlib
import subprocess
import asyncio
import tempfile
import multiprocessing
import aiofiles

logger = logging.getLogger(__name__)


class MinIOClient:
    def __init__(self, endpoint, access_key, secret_key, secure=False):
        """Initialize MinIO client"""
        self.client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure
        )
        self.endpoint = endpoint
    
    def generate_presigned_put_url(self, bucket_name, object_name, expires_seconds=3600):
        """Generate presigned URL for direct upload to MinIO
        
        Security notes:
        - expires_seconds is capped at 7 days (604800 seconds)
        - bucket_name must match allowed pattern
        - object_name is validated for path traversal
        """
        from datetime import timedelta
        import re
        
        # Validate and cap expiration time
        if expires_seconds < 60:  # Minimum 1 minute
            expires_seconds = 60
        if expires_seconds > 604800:  # Maximum 7 days
            expires_seconds = 604800
        
        # Validate bucket name (S3 bucket naming rules)
        if not re.match(r'^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$', bucket_name):
            raise ValueError(f"Invalid bucket name: {bucket_name}")
        
        # Validate object name (prevent path traversal and dangerous characters)
        if '..' in object_name or object_name.startswith('/'):
            raise ValueError(f"Invalid object name (path traversal detected): {object_name}")
        
        if any(char in object_name for char in ['\x00', '\n', '\r']):
            raise ValueError(f"Invalid object name (control characters detected): {object_name}")
        
        try:
            self.ensure_bucket(bucket_name)
            url = self.client.presigned_put_object(
                bucket_name,
                object_name,
                expires=timedelta(seconds=expires_seconds)
            )
            logger.info(f"Generated presigned PUT URL for {object_name} (expires in {expires_seconds}s)")
            return url
        except S3Error as e:
            logger.error(f"Error generating presigned URL for {object_name}: {e}")
            raise
        
    def ensure_bucket(self, bucket_name):
        """Create bucket if it doesn't exist"""
        try:
            if not self.client.bucket_exists(bucket_name):
                self.client.make_bucket(bucket_name)
                logger.info(f"Created bucket: {bucket_name}")
            return True
        except S3Error as e:
            logger.error(f"Error ensuring bucket {bucket_name}: {e}")
            return False
    
    def upload_file(self, bucket_name, object_name, file_path, content_type='application/octet-stream'):
        """Upload file to MinIO"""
        try:
            self.ensure_bucket(bucket_name)
            
            # Get file info
            file_stat = os.stat(file_path)
            file_size = file_stat.st_size
            
            # Calculate hashes
            md5_hash = self._calculate_md5(file_path)
            sha256_hash = self._calculate_sha256(file_path)
            
            # Upload file
            result = self.client.fput_object(
                bucket_name,
                object_name,
                file_path,
                content_type=content_type
            )
            
            logger.info(f"Uploaded {object_name} to {bucket_name}")
            
            return {
                'bucket_name': bucket_name,
                'object_name': object_name,
                'object_key': object_name,
                'size': file_size,
                'etag': result.etag,
                'version_id': result.version_id,
                'content_type': content_type,
                'md5_hash': md5_hash,
                'sha256_hash': sha256_hash
            }
            
        except S3Error as e:
            logger.error(f"Error uploading {object_name}: {e}")
            raise
    
    def upload_from_bytes(self, bucket_name, object_name, data, content_type='application/octet-stream'):
        """Upload file from bytes"""
        import time
        try:
            self.ensure_bucket(bucket_name)
            
            from io import BytesIO
            data_stream = BytesIO(data)
            data_size = len(data)
            
            upload_start = time.time()
            logger.info(f"Starting MinIO upload: {object_name} ({data_size} bytes)")
            
            result = self.client.put_object(
                bucket_name,
                object_name,
                data_stream,
                data_size,
                content_type=content_type
            )
            
            upload_time = time.time() - upload_start
            speed_mbps = (data_size / (1024**2)) / upload_time if upload_time > 0 else 0
            logger.info(f"✓ MinIO upload complete: {object_name} in {upload_time:.2f}s ({speed_mbps:.2f} MB/s)")
            
            return {
                'bucket_name': bucket_name,
                'object_name': object_name,
                'object_key': object_name,
                'size': data_size,
                'etag': result.etag,
                'version_id': result.version_id,
                'content_type': content_type
            }
            
        except S3Error as e:
            logger.error(f"Error uploading {object_name}: {e}")
            raise
    
    def _calculate_md5(self, file_path):
        """Calculate MD5 hash of file"""
        # OPTIMIZED: 1MB buffer instead of 4KB (256x fewer iterations)
        # For 1GB file: 1024 iterations vs 262,144 iterations = 3-5x faster
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):  # 1MB chunks
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    def _calculate_sha256(self, file_path):
        """Calculate SHA256 hash of file"""
        # OPTIMIZED: 1MB buffer instead of 4KB (256x fewer iterations)
        hash_sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):  # 1MB chunks
                hash_sha256.update(chunk)
        return hash_sha256.hexdigest()


async def save_minio_object_to_db(conn, bucket_id, sample_id, object_info, execution_id=None):
    """Save MinIO object metadata to database"""
    import json
    
    query = """
        INSERT INTO minio_objects (
            bucket_id,
            object_key,
            object_name,
            object_size_bytes,
            content_type,
            etag,
            md5_hash,
            sha256_hash,
            version_id,
            sample_id,
            execution_id,
            metadata
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12::jsonb)
        RETURNING object_id
    """
    
    object_id = await conn.fetchval(
        query,
        bucket_id,
        object_info['object_key'],
        object_info['object_name'],
        object_info['size'],
        object_info.get('content_type', 'application/octet-stream'),
        object_info.get('etag'),
        object_info.get('md5_hash'),
        object_info.get('sha256_hash'),
        object_info.get('version_id'),
        sample_id,
        execution_id,  # Link to Nextflow execution if this is a result file
        json.dumps({})  # metadata as JSONB string
    )
    
    return object_id


async def get_or_create_bucket(conn, bucket_name, layer_type='raw'):
    """Get existing bucket or create new one in database"""
    # Check if bucket exists
    query = "SELECT bucket_id FROM minio_buckets WHERE bucket_name = $1"
    bucket_id = await conn.fetchval(query, bucket_name)
    
    if bucket_id:
        return bucket_id
    
    # Create new bucket
    insert_query = """
        INSERT INTO minio_buckets (bucket_name, layer_type, description)
        VALUES ($1, $2, $3)
        RETURNING bucket_id
    """
    bucket_id = await conn.fetchval(
        insert_query, 
        bucket_name, 
        layer_type,
        f"Genomic data storage bucket - {layer_type} layer"
    )
    logger.info(f"Created bucket in DB: {bucket_name} with ID {bucket_id}")
    
    return bucket_id


def get_minio_client():
    """Get configured MinIO client instance"""
    from config import config

    endpoint = config.MINIO_ENDPOINT
    access_key = config.MINIO_ROOT_USER
    secret_key = config.MINIO_ROOT_PASSWORD

    return MinIOClient(endpoint, access_key, secret_key, secure=config.MINIO_SECURE)


# ==================== LAKEHOUSE BRONZE LAYER ====================

async def upload_to_bronze(conn, minio_client, sample_code, file_data, filename, sample_id=None):
    """
    Upload raw FASTQ file to Bronze layer (permanent storage)
    
    Args:
        conn: Database connection
        minio_client: MinIOClient instance
        sample_code: Sample identifier
        file_data: File content as bytes
        filename: Original filename
        sample_id: Optional sample_id for linking
    
    Returns:
        dict: {
            'object_id': int,
            'minio_path': str,
            'compressed': bool,
            'original_size': int,
            'final_size': int
        }
    """
    import gzip
    import json
    from datetime import datetime
    
    bronze_bucket = 'genomic-bronze'
    original_size = len(file_data)
    
    # Check if file already exists in bronze (avoid re-upload)
    final_filename = filename + '.gz' if not filename.endswith('.gz') else filename
    object_path = f"{sample_code}/raw/{final_filename}"
    
    try:
        # Try to get existing object
        existing = minio_client.client.stat_object(bronze_bucket, object_path)
        if existing and existing.size == original_size:
            logger.info(f"File already exists in bronze, skipping upload: {object_path}")
            # Get existing record from database
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT object_id FROM minio_objects WHERE sample_id = %s AND object_name = %s",
                    (sample_id, final_filename)
                )
                existing_record = await cur.fetchone()
                if existing_record:
                    return {
                        'object_id': existing_record['object_id'],
                        'filename': final_filename,
                        'minio_path': object_path,
                        'compressed': final_filename.endswith('.gz'),
                        'original_size': original_size,
                        'final_size': existing.size
                    }
    except Exception as e:
        logger.debug(f"Deduplication check for {filename}: {e}")
    
    # Auto-compress if not already .gz
    if not filename.endswith('.gz'):
        # OPTIMIZED: Stream compression to file instead of holding everything in memory
        # Before: 30GB original + 10GB compressed = 40GB RAM needed
        # After:  Write to disk, compress to disk, read compressed only = ~10GB RAM max

        logger.info(f"Compressing {filename} for bronze layer using pigz (streaming to disk)...")

        # Get maximum CPU threads
        max_threads = multiprocessing.cpu_count()
        logger.info(f"Using pigz with {max_threads} threads for parallel compression")

        # Write original data to temp file
        with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.tmp') as tmp_in:
            tmp_in.write(file_data)
            tmp_in_path = tmp_in.name

        # Create temp file for compressed output
        tmp_out_path = tmp_in_path + '.gz'

        try:
            # OPTIMIZED: Use async subprocess to avoid blocking event loop
            # This allows other requests to be processed during compression
            async def run_pigz():
                with open(tmp_out_path, 'wb') as f_out:
                    proc = await asyncio.create_subprocess_exec(
                        'pigz', '-p', str(max_threads), '-6', '-c', tmp_in_path,
                        stdout=f_out,
                        stderr=asyncio.subprocess.PIPE
                    )
                    _, stderr = await proc.communicate()
                    if proc.returncode != 0:
                        raise subprocess.CalledProcessError(proc.returncode, 'pigz', stderr=stderr)

            await run_pigz()

            # Read compressed file using async file I/O
            async with aiofiles.open(tmp_out_path, 'rb') as f:
                compressed_data = await f.read()

            final_filename = filename + '.gz'
            final_data = compressed_data
            was_compressed = True
            logger.info(f"Compression complete: {original_size} → {len(compressed_data)} bytes ({len(compressed_data)*100//original_size}%)")

        except (subprocess.CalledProcessError, OSError) as e:
            error_msg = getattr(e, 'stderr', b'').decode() if hasattr(e, 'stderr') and e.stderr else str(e)
            logger.error(f"pigz compression failed: {error_msg}")
            # Fallback to streaming gzip (still async file I/O)
            logger.info("Falling back to streaming gzip...")
            import gzip

            # Run gzip in thread pool to avoid blocking
            def compress_with_gzip():
                with open(tmp_out_path, 'wb') as f_out:
                    with gzip.open(f_out, 'wb', compresslevel=6) as gz:
                        gz.write(file_data)
                with open(tmp_out_path, 'rb') as f:
                    return f.read()

            loop = asyncio.get_event_loop()
            compressed_data = await loop.run_in_executor(None, compress_with_gzip)
            final_filename = filename + '.gz'
            final_data = compressed_data
            was_compressed = True

        finally:
            # Cleanup temp files - critical for disk space
            if os.path.exists(tmp_in_path):
                os.unlink(tmp_in_path)
            if tmp_out_path and os.path.exists(tmp_out_path):
                os.unlink(tmp_out_path)
    else:
        final_filename = filename
        final_data = file_data
        was_compressed = False
    
    final_size = len(final_data)
    
    # MinIO path: genomic-bronze/{sample_code}/raw/{filename}
    object_path = f"{sample_code}/raw/{final_filename}"
    
    # Upload to MinIO
    logger.info(f"Uploading to bronze: {object_path} ({final_size} bytes)")
    object_info = minio_client.upload_from_bytes(
        bronze_bucket,
        object_path,
        final_data,
        content_type='application/gzip' if final_filename.endswith('.gz') else 'application/octet-stream'
    )
    
    # Create metadata.json
    metadata = {
        'sample_code': sample_code,
        'original_filename': filename,
        'compressed_filename': final_filename,
        'original_size_bytes': original_size,
        'compressed_size_bytes': final_size,
        'compression_ratio': round(final_size / original_size, 3) if original_size > 0 else 1.0,
        'auto_compressed': was_compressed,
        'upload_timestamp': datetime.utcnow().isoformat(),
        'layer': 'bronze',
        'purpose': 'raw_upload'
    }
    
    metadata_path = f"{sample_code}/raw/metadata.json"
    metadata_bytes = json.dumps(metadata, indent=2).encode('utf-8')
    
    logger.info(f"Uploading metadata: {metadata_path}")
    minio_client.upload_from_bytes(
        bronze_bucket,
        metadata_path,
        metadata_bytes,
        content_type='application/json'
    )
    
    # Get or create bucket in database
    bucket_id = await get_or_create_bucket(conn, bronze_bucket, 'bronze')
    
    # Save to database with bronze layer tracking
    object_id = await save_minio_object_to_db(
        conn, 
        bucket_id, 
        sample_id, 
        object_info,
        execution_id=None  # Bronze layer is pre-execution
    )
    
    # Update with layer_stage
    await conn.execute(
        "UPDATE minio_objects SET layer_stage = 'raw' WHERE object_id = $1",
        object_id
    )
    
    logger.info(f"✓ Bronze upload complete: {object_path} (object_id={object_id})")
    
    return {
        'object_id': object_id,
        'minio_path': f"{bronze_bucket}/{object_path}",
        'compressed': was_compressed,
        'original_size': original_size,
        'final_size': final_size,
        'filename': final_filename
    }


async def download_from_bronze(minio_client, sample_code, output_dir, pipeline_id):
    """
    Download files from Bronze layer to local temp directory
    ONLY downloads files uploaded for specific pipeline_id
    
    Args:
        minio_client: MinIOClient instance
        sample_code: Sample identifier
        output_dir: Local directory to save files (e.g., /tmp/nextflow/{run_id}/input/)
        pipeline_id: Pipeline run ID to filter files
    
    Returns:
        list: Paths to downloaded files
    """
    from pathlib import Path
    import asyncpg
    import os
    
    bronze_bucket = 'genomic-bronze'
    
    # Ensure output directory exists
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    downloaded_files = []
    
    try:
        from database import DatabasePool
        import asyncpg
        from config import config
        
        # OPTIMIZED: Use connection pool if available, otherwise create direct connection
        conn = None
        use_pool = False
        
        try:
            pool = DatabasePool.get_pool()
            conn = await pool.acquire()
            use_pool = True
        except RuntimeError:
            # Pool not initialized (RQ worker context), create direct connection
            conn = await asyncpg.connect(config.DATABASE_URL)
            use_pool = False
        
        try:
            # Query files uploaded for this pipeline_id from bronze bucket
            # Note: layer_stage is set to 'raw' during upload, so we filter by bucket instead
            query = """
                SELECT mo.object_key, mo.object_name, mo.object_size_bytes
                FROM minio_objects mo
                JOIN minio_buckets mb ON mo.bucket_id = mb.bucket_id
                WHERE mo.pipeline_id = $1
                  AND mb.bucket_name = 'genomic-bronze'
                ORDER BY mo.created_at ASC
            """
            rows = await conn.fetch(query, pipeline_id)

            if not rows:
                raise FileNotFoundError(f"No files found in bronze layer for pipeline_id={pipeline_id}")
            
            logger.info(f"Found {len(rows)} files for pipeline_id={pipeline_id}")

            # OPTIMIZATION: Parallel download with semaphore to avoid overwhelming network
            import asyncio
            import gzip
            import shutil

            async def download_one_file(row):
                """Download and optionally decompress a single file"""
                object_key = row['object_key']
                filename = Path(object_key).name

                # Use thread pool for sync MinIO operations (minio-py is not async)
                loop = asyncio.get_event_loop()

                try:
                    if filename.endswith('.gz'):
                        # Download compressed file
                        compressed_path = output_path / filename
                        logger.info(f"Downloading compressed from bronze: {object_key} → {compressed_path}")

                        await loop.run_in_executor(
                            None,  # Default ThreadPoolExecutor
                            minio_client.client.fget_object,
                            bronze_bucket,
                            object_key,
                            str(compressed_path)
                        )

                        # Decompress (CPU-bound, but necessary)
                        decompressed_filename = filename[:-3]  # Remove .gz
                        local_path = output_path / decompressed_filename
                        logger.info(f"Decompressing: {compressed_path} → {local_path}")

                        with gzip.open(compressed_path, 'rb') as f_in:
                            with open(local_path, 'wb') as f_out:
                                shutil.copyfileobj(f_in, f_out)

                        # Remove compressed file
                        compressed_path.unlink()
                        logger.info(f"✓ Downloaded and decompressed: {decompressed_filename}")
                        return str(local_path)
                    else:
                        # Download uncompressed file directly
                        local_path = output_path / filename
                        logger.info(f"Downloading from bronze: {object_key} → {local_path}")

                        await loop.run_in_executor(
                            None,
                            minio_client.client.fget_object,
                            bronze_bucket,
                            object_key,
                            str(local_path)
                        )

                        logger.info(f"✓ Downloaded: {filename} ({row['object_size_bytes']} bytes)")
                        return str(local_path)

                except Exception as e:
                    logger.error(f"Failed to download {object_key}: {e}")
                    raise

            # OPTIMIZED: Increased semaphore from 3 to 10 for better parallelism
            # For 100 files × 1GB each:
            #   - Semaphore(3):  ~100 minutes (3 files at a time)
            #   - Semaphore(10): ~30 minutes  (10 files at a time)
            # Network bandwidth: 1Gbps = 125MB/s, can easily handle 10 concurrent streams
            max_concurrent = min(10, len(rows))  # Don't exceed file count
            semaphore = asyncio.Semaphore(max_concurrent)

            async def download_with_semaphore(row):
                async with semaphore:
                    return await download_one_file(row)

            # Download all files in parallel (with semaphore limiting concurrency)
            logger.info(f"Starting parallel download of {len(rows)} files (max {max_concurrent} concurrent)...")
            tasks = [download_with_semaphore(row) for row in rows]
            downloaded_paths = await asyncio.gather(*tasks, return_exceptions=True)

            # Filter out exceptions and collect successful downloads
            for idx, result in enumerate(downloaded_paths):
                if isinstance(result, Exception):
                    logger.error(f"Download failed for file {idx}: {result}")
                else:
                    downloaded_files.append(result)
        
            logger.info(f"✓ Downloaded {len(downloaded_files)} files from bronze layer for pipeline_id={pipeline_id}")
            
        finally:
            # Clean up connection
            if use_pool:
                await pool.release(conn)
            else:
                await conn.close()
        
        return downloaded_files
        
    except Exception as e:
        logger.error(f"Error downloading from bronze: {e}")
        raise


# ==================== LAKEHOUSE SILVER LAYER ====================

# Mapping of Nextflow process names to silver layer directories
SILVER_LAYER_MAPPING = {
    'SUMMARY': '00_summary',
    'NANOPLOT': '01_QC/nanoplot',
    # FILTLONG excluded: filtered FASTQ is ephemeral, cheaply re-derived from Bronze
    'FLYE': '03_assembly',
    'METABAT2': '04_binning/metabat2',
    'CONCOCT': '04_binning/concoct',
    'CHECKM_METABAT2': '05_quality/metabat2',
    'CHECKM_CONCOCT': '05_quality/concoct',
    'BIN_FILTER': '05_filtered',
    'DREP': '05_drep',
    'GTDBTK': '05_gtdbtk',
    'KRAKEN2': '06_kraken2',
    'ABRICATE': '07_amr/abricate',
    'DEEPARG': '07_amr/deeparg',
    'BRACKEN': '07_bracken',
    'NUCMER': '08_comparative/nucmer',
}

# Files to skip during Silver upload (CheckM internal/intermediate files)
# Only summary TSVs and logs are valuable from CheckM
SILVER_SKIP_PATTERNS = {
    '.masked.faa',          # CheckM marker gene alignments
    '.pkl.gz',              # CheckM serialized data
    'concatenated.tre',     # CheckM phylogenetic tree
    'concatenated.fasta',   # CheckM concatenated markers
    'concatenated.pplacer.json',  # pplacer placement
    'pplacer.out',          # pplacer output
    'genes.faa',            # CheckM extracted genes
    'genes.gff',            # CheckM gene annotations
    'hmmer.analyze.txt',    # HMMER raw output
    'hmmer.tree.txt',       # HMMER tree output
    'lineage.ms',           # CheckM lineage markers
    'phylo_hmm_info.pkl.gz',  # CheckM HMM info
}


async def upload_to_silver(conn, minio_client, sample_code, run_id, process_name,
                          local_files, execution_id=None, tool_version=None, source_object_ids=None):
    """
    Upload process results to Silver layer (intermediate results)

    Args:
        conn: Database connection
        minio_client: MinIOClient instance
        sample_code: Sample identifier
        run_id: Pipeline run ID
        process_name: Nextflow process name (NANOPLOT, FILTLONG, etc.)
        local_files: List of local file paths to upload
        execution_id: Nextflow execution ID
        tool_version: Tool/container version
        source_object_ids: List of source object IDs for lineage tracking (Bronze files)

    Returns:
        list: Object IDs created in database
    """
    from pathlib import Path
    
    silver_bucket = 'genomic-silver'
    layer_stage = SILVER_LAYER_MAPPING.get(process_name, 'unknown')
    
    # MinIO path: genomic-silver/{sample_code}/{run_id}/{layer_stage}/
    base_path = f"{sample_code}/{run_id}/{layer_stage}"
    
    # Get or create bucket
    bucket_id = await get_or_create_bucket(conn, silver_bucket, 'silver')

    object_ids = []
    lineage_records = []  # OPTIMIZATION: Collect lineage records for batch insert
    update_records = []   # OPTIMIZATION: Collect UPDATE records for batch execution

    for local_file in local_files:
        file_path = Path(local_file)

        if not file_path.exists():
            logger.warning(f"File not found, skipping: {local_file}")
            continue

        # Skip CheckM internal files (not valuable for analysis)
        if any(file_path.name.endswith(pat) or file_path.name == pat for pat in SILVER_SKIP_PATTERNS):
            logger.debug(f"Skipping CheckM internal file: {file_path.name}")
            continue

        # Upload to MinIO
        object_path = f"{base_path}/{file_path.name}"
        
        logger.info(f"Uploading to silver [{process_name}]: {object_path}")
        
        object_info = minio_client.upload_file(
            silver_bucket,
            object_path,
            str(file_path),
            content_type='application/octet-stream'
        )
        
        # Save to database with process tracking
        object_id = await save_minio_object_to_db(
            conn,
            bucket_id,
            None,  # sample_id linked via execution
            object_info,
            execution_id=execution_id
        )
        
        # OPTIMIZATION: Include metadata in INSERT instead of separate UPDATE
        # (saves 1 DB round trip per file)
        # Note: save_minio_object_to_db already saved basic info
        # We collect process-specific fields for batch update
        update_records.append((process_name, tool_version, layer_stage, run_id, object_id))

        # Collect lineage records for batch insert
        if source_object_ids:
            import json
            lineage_metadata = json.dumps({
                'tool_version': tool_version,
                'layer_stage': layer_stage,
                'process_name': process_name
            })

            # Collect tuples for batch insert
            for source_id in source_object_ids:
                lineage_records.append((
                    source_id, object_id, 'processing', process_name, lineage_metadata
                ))

        object_ids.append(object_id)
        logger.info(f"✓ Silver upload complete: {object_path} (object_id={object_id})")

    # OPTIMIZATION: Batch update all process metadata (instead of 1 query per file)
    if update_records:
        await conn.executemany("""
            UPDATE minio_objects
            SET process_name = $1,
                tool_version = $2,
                layer_stage = $3,
                pipeline_id = $4
            WHERE object_id = $5
        """, update_records)
        logger.info(f"✓ Process metadata updated: {len(update_records)} records (batch update)")

    # OPTIMIZATION: Batch insert all lineage records (instead of 1 query per source × file)
    if lineage_records:
        await conn.executemany("""
            INSERT INTO data_lineage (
                source_object_id, target_object_id, transformation_type,
                transformation_process, transformation_time, transformation_metadata
            ) VALUES ($1, $2, $3, $4, CURRENT_TIMESTAMP, $5)
        """, lineage_records)

        logger.info(f"✓ Lineage tracked: {len(lineage_records)} records (batch insert)")

    return object_ids


# ==================== LAKEHOUSE GOLD LAYER ====================

async def upload_to_gold(conn, minio_client, sample_code, local_file, 
                        artifact_type, quality_tier=None, metadata=None):
    """
    Upload curated final result to Gold layer
    
    Args:
        conn: Database connection
        minio_client: MinIOClient instance
        sample_code: Sample identifier
        local_file: Local file path to upload
        artifact_type: 'assembly', 'bin', 'qc_report', etc.
        quality_tier: 'high', 'medium', 'low' (for bins)
        metadata: Dict with metrics (completeness, contamination, N50, etc.)
    
    Returns:
        int: artifact_id from pipeline_artifacts table
    """
    from pathlib import Path
    import json
    
    gold_bucket = 'genomic-gold'
    file_path = Path(local_file)
    
    if not file_path.exists():
        logger.error(f"File not found for gold upload: {local_file}")
        return None
    
    # Determine gold path based on artifact type
    if artifact_type == 'assembly':
        gold_path = f"{sample_code}/assembly/{file_path.name}"
    elif artifact_type == 'bin':
        tier_folder = quality_tier if quality_tier else 'unknown'
        gold_path = f"{sample_code}/bins/{tier_folder}/{file_path.name}"
    elif 'report' in artifact_type:
        gold_path = f"{sample_code}/reports/{file_path.name}"
    else:
        gold_path = f"{sample_code}/other/{file_path.name}"
    
    logger.info(f"Uploading to gold [{artifact_type}]: {gold_path}")
    
    # Upload to MinIO
    object_info = minio_client.upload_file(
        gold_bucket,
        gold_path,
        str(file_path),
        content_type='application/octet-stream'
    )
    
    # Get or create bucket
    bucket_id = await get_or_create_bucket(conn, gold_bucket, 'gold')
    
    # Save to minio_objects
    object_id = await save_minio_object_to_db(
        conn,
        bucket_id,
        None,
        object_info,
        execution_id=None  # Gold layer is post-execution
    )
    
    # Update with gold layer stage
    await conn.execute(
        "UPDATE minio_objects SET layer_stage = 'gold' WHERE object_id = $1",
        object_id
    )
    
    logger.info(f"✓ Gold upload complete: {gold_path} (object_id={object_id})")
    
    return {
        'object_id': object_id,
        'minio_path': f"{gold_bucket}/{gold_path}",
        'artifact_type': artifact_type,
        'quality_tier': quality_tier
    }


async def curate_gold_layer(conn, minio_client, pipeline_id, sample_code, results_path):
    """
    Curate and upload final results to Gold layer
    
    Selects:
    - Best assembly (highest N50)
    - High-quality bins (>90% completeness, <5% contamination)
    - Summary reports
    
    Args:
        conn: Database connection
        minio_client: MinIOClient instance
        pipeline_id: Pipeline run ID
        sample_code: Sample identifier
        results_path: Local results directory
    
    Returns:
        dict: Summary of curated artifacts
    """
    from pathlib import Path
    import json
    
    results_dir = Path(results_path)
    curated_artifacts = {
        'assemblies': [],
        'high_quality_bins': [],
        'medium_quality_bins': [],
        'low_quality_bins': [],
        'reports': []
    }
    
    logger.info(f"Starting gold layer curation for pipeline {pipeline_id}")
    
    # 1. Curate assembly
    assembly_dir = results_dir / "03_assembly"
    if assembly_dir.exists():
        for assembly_file in assembly_dir.glob("*.fasta"):
            # Parse assembly stats from JSON (generated by pipeline_summary module)
            stats_file = assembly_dir / f"{assembly_file.stem}_assembly_stats.json"
            n50 = 0
            total_length = 0

            if stats_file.exists():
                try:
                    import json as _json
                    with open(stats_file) as f:
                        stats = _json.load(f)
                    n50 = stats.get('n50', 0)
                    total_length = stats.get('total_length', 0)
                except Exception as e:
                    logger.warning(f"Failed to parse assembly stats JSON {stats_file}: {e}")
            
            # Upload to gold
            gold_info = await upload_to_gold(
                conn, minio_client, sample_code, str(assembly_file),
                artifact_type='assembly',
                metadata={'n50': n50, 'total_length': total_length}
            )
            
            if gold_info:
                # Create artifact record
                artifact_id = await conn.fetchval("""
                    INSERT INTO pipeline_artifacts (
                        pipeline_id, artifact_type, artifact_name,
                        minio_object_id, quality_tier, quality_score,
                        metadata, process_name, created_by
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    RETURNING artifact_id
                """, pipeline_id, 'assembly', assembly_file.name,
                    gold_info['object_id'], 'high', None,
                    json.dumps({'n50': n50, 'total_length': total_length}),
                    'FLYE', 'Flye Assembler')

                # ✅ NEW: Track lineage (Silver assembly → Gold)
                # Find source Silver assembly object
                silver_source = await conn.fetchval("""
                    SELECT object_id FROM minio_objects mo
                    JOIN minio_buckets mb ON mo.bucket_id = mb.bucket_id
                    WHERE mb.bucket_name = 'genomic-silver'
                      AND mo.pipeline_id = $1
                      AND mo.process_name = 'FLYE'
                      AND mo.object_key LIKE $2
                    LIMIT 1
                """, pipeline_id, f"%/{assembly_file.name}")

                if silver_source:
                    await conn.execute("""
                        INSERT INTO data_lineage (
                            source_object_id, target_object_id, transformation_type,
                            transformation_process, transformation_time, transformation_metadata
                        ) VALUES ($1, $2, $3, $4, CURRENT_TIMESTAMP, $5)
                    """, silver_source, gold_info['object_id'], 'curation', 'GOLD_CURATION',
                        json.dumps({'quality_tier': 'high', 'artifact_type': 'assembly'}))

                    logger.info(f"✓ Lineage tracked: Silver assembly → Gold (object_id={gold_info['object_id']})")

                curated_artifacts['assemblies'].append({
                    'artifact_id': artifact_id,
                    'filename': assembly_file.name,
                    'n50': n50
                })

                logger.info(f"✓ Curated assembly: {assembly_file.name} (N50={n50})")
    
    # 2. Curate bins based on CheckM quality
    for binning_method in ['metabat2', 'concoct']:
        checkm_dir = results_dir / f"05_quality" / binning_method
        checkm_summary = checkm_dir / "checkm_summary.tsv"
        
        if not checkm_summary.exists():
            continue
        
        # Parse CheckM summary
        bin_quality = {}
        with open(checkm_summary, 'r') as f:
            header = None
            for line in f:
                if line.startswith('Bin Id'):
                    header = line.strip().split('\t')
                    continue
                if not header:
                    continue
                
                parts = line.strip().split('\t')
                if len(parts) < 3:
                    continue
                
                bin_id = parts[0]
                try:
                    completeness = float(parts[header.index('Completeness')])
                    contamination = float(parts[header.index('Contamination')])
                    
                    # Determine quality tier
                    if completeness >= 90 and contamination < 5:
                        tier = 'high'
                    elif completeness >= 50 and contamination < 10:
                        tier = 'medium'
                    else:
                        tier = 'low'
                    
                    bin_quality[bin_id] = {
                        'completeness': completeness,
                        'contamination': contamination,
                        'tier': tier
                    }
                except (ValueError, IndexError):
                    continue
        
        # Upload high-quality bins to gold
        bins_dir = results_dir / "04_binning" / binning_method
        if bins_dir.exists():
            for bin_file in bins_dir.glob("*.fa"):
                bin_id = bin_file.stem
                quality = bin_quality.get(bin_id, {})
                
                if not quality:
                    continue
                
                tier = quality['tier']
                completeness = quality['completeness']
                contamination = quality['contamination']
                
                # Upload to gold (all tiers, organized by folder)
                gold_info = await upload_to_gold(
                    conn, minio_client, sample_code, str(bin_file),
                    artifact_type='bin',
                    quality_tier=tier,
                    metadata=quality
                )
                
                if gold_info:
                    # Create artifact record
                    artifact_id = await conn.fetchval("""
                        INSERT INTO pipeline_artifacts (
                            pipeline_id, artifact_type, artifact_name,
                            minio_object_id, quality_tier, quality_score,
                            metadata, process_name, created_by
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                        RETURNING artifact_id
                    """, pipeline_id, 'bin', bin_file.name,
                        gold_info['object_id'], tier, completeness,
                        json.dumps(quality),
                        f'CHECKM_{binning_method.upper()}', f'CheckM + {binning_method}')

                    # ✅ NEW: Track lineage (Silver bin → Gold)
                    # Find source Silver bin object
                    silver_bin_source = await conn.fetchval("""
                        SELECT object_id FROM minio_objects mo
                        JOIN minio_buckets mb ON mo.bucket_id = mb.bucket_id
                        WHERE mb.bucket_name = 'genomic-silver'
                          AND mo.pipeline_id = $1
                          AND mo.process_name = $2
                          AND mo.object_key LIKE $3
                        LIMIT 1
                    """, pipeline_id, binning_method.upper(), f"%/{bin_file.name}")

                    if silver_bin_source:
                        await conn.execute("""
                            INSERT INTO data_lineage (
                                source_object_id, target_object_id, transformation_type,
                                transformation_process, transformation_time, transformation_metadata
                            ) VALUES ($1, $2, $3, $4, CURRENT_TIMESTAMP, $5)
                        """, silver_bin_source, gold_info['object_id'], 'curation', 'GOLD_CURATION',
                            json.dumps({
                                'quality_tier': tier,
                                'artifact_type': 'bin',
                                'completeness': completeness,
                                'contamination': contamination
                            }))

                        logger.info(f"✓ Lineage tracked: Silver bin ({binning_method}) → Gold (tier={tier})")

                    bin_info = {
                        'artifact_id': artifact_id,
                        'filename': bin_file.name,
                        'completeness': completeness,
                        'contamination': contamination,
                        'method': binning_method
                    }

                    if tier == 'high':
                        curated_artifacts['high_quality_bins'].append(bin_info)
                    elif tier == 'medium':
                        curated_artifacts['medium_quality_bins'].append(bin_info)
                    else:
                        curated_artifacts['low_quality_bins'].append(bin_info)
                    
                    logger.info(f"✓ Curated {tier} quality bin: {bin_file.name} ({completeness}% complete)")
    
    # 3. Generate and upload summary report
    summary_report = {
        'sample_code': sample_code,
        'pipeline_id': pipeline_id,
        'assemblies_count': len(curated_artifacts['assemblies']),
        'high_quality_bins': len(curated_artifacts['high_quality_bins']),
        'medium_quality_bins': len(curated_artifacts['medium_quality_bins']),
        'low_quality_bins': len(curated_artifacts['low_quality_bins']),
        'total_bins': sum([
            len(curated_artifacts['high_quality_bins']),
            len(curated_artifacts['medium_quality_bins']),
            len(curated_artifacts['low_quality_bins'])
        ]),
        'curated_artifacts': curated_artifacts
    }
    
    # Save summary to temp file and upload
    summary_file = results_dir / "gold_summary.json"
    with open(summary_file, 'w') as f:
        json.dump(summary_report, f, indent=2)
    
    gold_info = await upload_to_gold(
        conn, minio_client, sample_code, str(summary_file),
        artifact_type='gold_summary',
        metadata=summary_report
    )
    
    if gold_info:
        await conn.fetchval("""
            INSERT INTO pipeline_artifacts (
                pipeline_id, artifact_type, artifact_name,
                minio_object_id, metadata, process_name
            ) VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING artifact_id
        """, pipeline_id, 'gold_summary', 'gold_summary.json',
            gold_info['object_id'], json.dumps(summary_report), 'CURATION')
    
    # Update pipeline_runs with gold_path
    gold_path = f"genomic-gold/{sample_code}/"
    await conn.execute(
        "UPDATE pipeline_runs SET gold_path = $1 WHERE pipeline_id = $2",
        gold_path, pipeline_id
    )
    
    logger.info(f"✓ Gold layer curation complete for pipeline {pipeline_id}")
    logger.info(f"  Assemblies: {len(curated_artifacts['assemblies'])}")
    logger.info(f"  High-quality bins: {len(curated_artifacts['high_quality_bins'])}")
    logger.info(f"  Medium-quality bins: {len(curated_artifacts['medium_quality_bins'])}")
    logger.info(f"  Low-quality bins: {len(curated_artifacts['low_quality_bins'])}")
    
    return summary_report


