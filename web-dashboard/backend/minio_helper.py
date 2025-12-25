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
import tempfile
import multiprocessing

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
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    
    def _calculate_sha256(self, file_path):
        """Calculate SHA256 hash of file"""
        hash_sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
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
        existing = minio_client.stat_object(bronze_bucket, object_path)
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
    except Exception:
        pass  # File doesn't exist, continue with upload
    
    # Auto-compress if not already .gz
    if not filename.endswith('.gz'):
        # Check file size to prevent memory exhaustion
        max_size = 100 * 1024 * 1024 * 1024  # 100 GB
        if original_size > max_size:
            raise ValueError(f"File too large for in-memory compression: {original_size} bytes (max: {max_size})")
        
        logger.info(f"Compressing {filename} for bronze layer using pigz...")
        
        # Get maximum CPU threads
        max_threads = multiprocessing.cpu_count()
        logger.info(f"Using pigz with {max_threads} threads for parallel compression")
        
        # Write to temp file and compress with pigz (parallel gzip)
        with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.tmp') as tmp_in:
            tmp_in.write(file_data)
            tmp_in_path = tmp_in.name
        
        tmp_out_path = None  # Initialize to prevent NameError in finally block
        
        try:
            # Run pigz with maximum threads and best speed/compression balance
            result = subprocess.run(
                ['pigz', '-p', str(max_threads), '-6', '-c', tmp_in_path],
                capture_output=True,
                check=True
            )
            compressed_data = result.stdout
            final_filename = filename + '.gz'
            final_data = compressed_data
            was_compressed = True
            logger.info(f"Compression complete: {len(file_data)} → {len(compressed_data)} bytes")
        except subprocess.CalledProcessError as e:
            logger.error(f"pigz compression failed: {e.stderr.decode()}")
            # Fallback to gzip if pigz fails
            logger.info("Falling back to standard gzip...")
            import gzip
            compressed_data = gzip.compress(file_data, compresslevel=6)
            final_filename = filename + '.gz'
            final_data = compressed_data
            was_compressed = True
        except FileNotFoundError:
            # pigz not installed, use gzip
            logger.warning("pigz not found, using standard gzip (slower)")
            import gzip
            compressed_data = gzip.compress(file_data, compresslevel=6)
            final_filename = filename + '.gz'
            final_data = compressed_data
            was_compressed = True
        finally:
            # Cleanup temp files
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


async def download_from_bronze(minio_client, sample_code, output_dir):
    """
    Download files from Bronze layer to local temp directory
    
    Args:
        minio_client: MinIOClient instance
        sample_code: Sample identifier
        output_dir: Local directory to save files (e.g., /tmp/nextflow/{run_id}/input/)
    
    Returns:
        list: Paths to downloaded files
    """
    from pathlib import Path
    
    bronze_bucket = 'genomic-bronze'
    prefix = f"{sample_code}/raw/"
    
    # Ensure output directory exists
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    downloaded_files = []
    
    try:
        # List objects in MinIO with prefix
        objects = list(minio_client.client.list_objects(bronze_bucket, prefix=prefix, recursive=True))
        
        # Build list of files to download
        # CRITICAL FIX: Prefer .gz version if both .fastq and .fastq.gz exist
        files_to_download = {}
        for obj in objects:
            # Skip metadata.json
            if obj.object_name.endswith('metadata.json'):
                continue
            
            filename = Path(obj.object_name).name
            # Get base name without .gz extension
            if filename.endswith('.gz'):
                base_name = filename[:-3]  # Remove .gz
            else:
                base_name = filename
            
            # Store compressed version if available, else uncompressed
            if base_name not in files_to_download or filename.endswith('.gz'):
                files_to_download[base_name] = obj
        
        # Download selected files
        for base_name, obj in files_to_download.items():
            filename = Path(obj.object_name).name
            local_path = output_path / filename
            
            logger.info(f"Downloading from bronze: {obj.object_name} → {local_path}")
            
            minio_client.client.fget_object(
                bronze_bucket,
                obj.object_name,
                str(local_path)
            )

            # Keep files compressed - Nextflow expects .fastq.gz format
            downloaded_files.append(str(local_path))
            logger.info(f"✓ Downloaded: {filename} ({obj.size} bytes)")
        
        if not downloaded_files:
            raise FileNotFoundError(f"No files found in bronze layer for sample {sample_code}")
        
        logger.info(f"✓ Downloaded {len(downloaded_files)} files from bronze layer (deduplicated)")
        return downloaded_files
        
    except Exception as e:
        logger.error(f"Error downloading from bronze: {e}")
        raise


# ==================== LAKEHOUSE SILVER LAYER ====================

# Mapping of Nextflow process names to silver layer directories
SILVER_LAYER_MAPPING = {
    'NANOPLOT': '01_qc',
    'FILTLONG': '02_filtered',
    'FLYE': '03_assembly',
    'METABAT2': '04_binning/metabat2',
    'CONCOCT': '04_binning/concoct',
    'CHECKM_METABAT2': '05_quality/metabat2',
    'CHECKM_CONCOCT': '05_quality/concoct',
    'KRAKEN2': '06_taxonomy',
    'BRACKEN': '07_abundance'
}


async def upload_to_silver(conn, minio_client, sample_code, run_id, process_name, 
                          local_files, execution_id=None, tool_version=None):
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
    
    for local_file in local_files:
        file_path = Path(local_file)
        
        if not file_path.exists():
            logger.warning(f"File not found, skipping: {local_file}")
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
        
        # Update with process info
        await conn.execute("""
            UPDATE minio_objects 
            SET process_name = $1, 
                tool_version = $2, 
                layer_stage = $3
            WHERE object_id = $4
        """, process_name, tool_version, layer_stage, object_id)
        
        object_ids.append(object_id)
        logger.info(f"✓ Silver upload complete: {object_path} (object_id={object_id})")
    
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
            # Parse assembly info for N50
            info_file = assembly_file.with_suffix('.info.txt')
            n50 = 0
            total_length = 0
            
            if info_file.exists():
                with open(info_file, 'r') as f:
                    for line in f:
                        if 'N50:' in line:
                            n50 = int(line.split(':')[1].strip())
                        if 'Total length:' in line:
                            total_length = int(line.split(':')[1].strip())
            
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


