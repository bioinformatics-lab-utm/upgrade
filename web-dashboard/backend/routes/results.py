# Pipeline Results API Routes
# Handles viewing and downloading of pipeline execution results

from sanic import Blueprint, response
from sanic.response import json, file, html
from pathlib import Path
import os
import logging
from datetime import datetime
import time
from functools import lru_cache

logger = logging.getLogger(__name__)

from auth import protected

results_bp = Blueprint('results', url_prefix='/api/pipeline/results')

# Results directory configuration
RESULTS_DIR = Path('/results')  # Mounted from host at /home/nicolaedrabcinski/upgrade/results

# File types that can be viewed directly in browser
VIEWABLE_EXTENSIONS = {'.html', '.txt', '.log', '.tsv', '.csv', '.json', '.xml', '.gff', '.kreport'}
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.svg', '.gif'}
PDF_EXTENSIONS = {'.pdf'}

# OPTIMIZED: Simple in-memory cache for file listings
# Avoids repeated os.walk() calls (100x faster for repeated requests)
_file_listing_cache = {}
_cache_ttl_seconds = 60  # Cache for 60 seconds


def get_cached_file_listing(run_path: Path, run_id: str):
    """Get file listing from cache or scan directory"""
    cache_key = str(run_path)
    now = time.time()

    # Check cache
    if cache_key in _file_listing_cache:
        cached_data, cached_time = _file_listing_cache[cache_key]
        if now - cached_time < _cache_ttl_seconds:
            logger.debug(f"Cache hit for {run_id} file listing")
            return cached_data

    # Cache miss - scan directory
    logger.debug(f"Cache miss for {run_id} - scanning directory")
    files = scan_run_directory(run_path)

    # Store in cache
    _file_listing_cache[cache_key] = (files, now)

    # Cleanup old cache entries (prevent memory leak)
    if len(_file_listing_cache) > 100:
        old_keys = [k for k, (_, t) in _file_listing_cache.items() if now - t > _cache_ttl_seconds * 2]
        for k in old_keys:
            del _file_listing_cache[k]

    return files


def invalidate_file_cache(run_id: str = None):
    """Invalidate file listing cache (call after file changes)"""
    global _file_listing_cache
    if run_id:
        cache_key = str(RESULTS_DIR / run_id)
        if cache_key in _file_listing_cache:
            del _file_listing_cache[cache_key]
    else:
        _file_listing_cache = {}


def format_file_size(size_bytes):
    """Format file size in human-readable format"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


def scan_run_directory(run_path):
    """Recursively scan run directory and categorize files"""
    files = {}
    
    for root, dirs, filenames in os.walk(run_path):
        for filename in filenames:
            full_path = Path(root) / filename
            relative_path = full_path.relative_to(run_path)
            
            # Get file stats
            stat = full_path.stat()
            ext = full_path.suffix.lower()
            
            # Determine if file is viewable
            viewable = ext in VIEWABLE_EXTENSIONS or ext in IMAGE_EXTENSIONS
            
            files[str(relative_path)] = {
                'name': filename,
                'path': str(relative_path),
                'full_path': str(full_path),
                'size': format_file_size(stat.st_size),
                'size_bytes': stat.st_size,
                'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                'extension': ext,
                'viewable': viewable,
                'is_image': ext in IMAGE_EXTENSIONS,
                'is_pdf': ext in PDF_EXTENSIONS,
                'is_report': ext in {'.html', '.pdf'}
            }
    
    return files


@results_bp.route('/')
@protected
async def list_runs(request):
    """List all available pipeline runs with status from pipeline_runs table"""
    try:
        db_pool = request.app.ctx.db_pool
        
        # Get pipeline runs from database
        async with db_pool.acquire() as conn:
            db_runs = await conn.fetch("""
                SELECT 
                    pipeline_id,
                    sample_name,
                    status,
                    location,
                    results_path,
                    started_at,
                    completed_at,
                    error_message
                FROM pipeline_runs
                ORDER BY started_at DESC
            """)
        
        # Create lookup by sample_name and results directory
        runs_by_name = {row['sample_name']: row for row in db_runs}
        runs_by_path = {}
        for row in db_runs:
            if row['results_path']:
                path_name = Path(row['results_path']).name
                runs_by_path[path_name] = row
        
        runs = []
        
        # Scan filesystem for results directories
        if RESULTS_DIR.exists():
            for run_dir in sorted(RESULTS_DIR.iterdir(), reverse=True):
                if run_dir.is_dir() and not run_dir.name.startswith('.'):
                    # Count files in run
                    file_count = sum(1 for _ in run_dir.rglob('*') if _.is_file())
                    
                    # Detect stages
                    stages = [d.name for d in run_dir.iterdir() if d.is_dir() and not d.name.startswith('.')]
                    
                    # Try to get sample name from directory name or DB
                    sample_name = run_dir.name
                    db_run = runs_by_path.get(run_dir.name) or runs_by_name.get(run_dir.name)
                    
                    # Use database status if available, otherwise infer from filesystem
                    if db_run:
                        status = db_run['status']
                        date = db_run['started_at'].isoformat() if db_run['started_at'] else datetime.fromtimestamp(run_dir.stat().st_mtime).isoformat()
                        location = db_run['location']
                        error_message = db_run['error_message']
                    else:
                        status = 'completed'  # Assume completed if in results dir but not in DB
                        date = datetime.fromtimestamp(run_dir.stat().st_mtime).isoformat()
                        location = None
                        error_message = None
                    
                    runs.append({
                        'id': run_dir.name,
                        'path': str(run_dir),
                        'date': date,
                        'file_count': file_count,
                        'stages': len(stages),
                        'stage_names': stages,
                        'sample_name': sample_name,
                        'status': status,
                        'location': location,
                        'error_message': error_message
                    })
        
        return json({'runs': runs, 'count': len(runs)})
    
    except Exception as e:
        logger.error(f"Error listing runs: {str(e)}")
        return json({'error': str(e)}, status=500)


@results_bp.route('/<run_id>/files')
@protected
async def list_run_files(request, run_id):
    """List all files in a specific run - OPTIMIZED with caching"""
    try:
        run_path = RESULTS_DIR / run_id

        if not run_path.exists():
            return json({'error': 'Run not found'}, status=404)

        # OPTIMIZED: Use cached file listing (100x faster for repeated requests)
        files = get_cached_file_listing(run_path, run_id)

        return json({
            'run_id': run_id,
            'files': files,
            'count': len(files),
            'cached': True  # Indicate response may be cached
        })

    except Exception as e:
        logger.error(f"Error listing run files: {str(e)}")
        return json({'error': str(e)}, status=500)


@results_bp.route('/<run_id>/view')
@protected
async def view_file(request, run_id):
    """View a file (HTML, text, images) in browser"""
    try:
        file_path = request.args.get('path')
        if not file_path:
            return json({'error': 'Path parameter required'}, status=400)
        
        full_path = RESULTS_DIR / run_id / file_path
        
        if not full_path.exists():
            return json({'error': 'File not found'}, status=404)
        
        # Security check: ensure file is within results directory
        if not str(full_path.resolve()).startswith(str(RESULTS_DIR.resolve())):
            return json({'error': 'Access denied'}, status=403)
        
        ext = full_path.suffix.lower()
        
        # Serve HTML directly
        if ext == '.html':
            return await file(str(full_path), mime_type='text/html')
        
        # Serve images
        if ext in IMAGE_EXTENSIONS:
            mime_types = {
                '.png': 'image/png',
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.svg': 'image/svg+xml',
                '.gif': 'image/gif'
            }
            return await file(str(full_path), mime_type=mime_types.get(ext, 'application/octet-stream'))
        
        # Serve text files
        if ext in {'.txt', '.log', '.tsv', '.csv', '.json', '.xml', '.gff', '.kreport'}:
            return await file(str(full_path), mime_type='text/plain')
        
        # Serve PDF
        if ext == '.pdf':
            return await file(str(full_path), mime_type='application/pdf')
        
        return json({'error': 'File type not supported for viewing'}, status=400)
    
    except Exception as e:
        logger.error(f"Error viewing file: {str(e)}")
        return json({'error': str(e)}, status=500)


@results_bp.route('/<run_id>/download')
@protected
async def download_file(request, run_id):
    """Download a file"""
    try:
        file_path = request.args.get('path')
        if not file_path:
            return json({'error': 'Path parameter required'}, status=400)
        
        full_path = RESULTS_DIR / run_id / file_path
        
        if not full_path.exists():
            return json({'error': 'File not found'}, status=404)
        
        # Security check
        if not str(full_path.resolve()).startswith(str(RESULTS_DIR.resolve())):
            return json({'error': 'Access denied'}, status=403)
        
        return await file(
            str(full_path),
            filename=full_path.name,
            mime_type='application/octet-stream'
        )
    
    except Exception as e:
        logger.error(f"Error downloading file: {str(e)}")
        return json({'error': str(e)}, status=500)


@results_bp.route('/<run_id>/summary')
@protected
async def get_run_summary(request, run_id):
    """Get summary statistics for a run"""
    try:
        run_path = RESULTS_DIR / run_id
        
        if not run_path.exists():
            return json({'error': 'Run not found'}, status=404)
        
        files = scan_run_directory(run_path)
        
        # Categorize files by stage
        stages = {}
        for file_path, file_info in files.items():
            stage = file_path.split('/')[0] if '/' in file_path else 'root'
            if stage not in stages:
                stages[stage] = {
                    'name': stage,
                    'files': [],
                    'total_size': 0,
                    'report_count': 0
                }
            stages[stage]['files'].append(file_info)
            stages[stage]['total_size'] += file_info['size_bytes']
            if file_info['is_report']:
                stages[stage]['report_count'] += 1
        
        # Format stage sizes
        for stage in stages.values():
            stage['total_size'] = format_file_size(stage['total_size'])
            stage['file_count'] = len(stage['files'])
        
        # Find key reports
        key_reports = {
            'nanoplot': None,
            'nextflow_report': None,
            'nextflow_timeline': None,
            'kraken': None,
            'checkm': None,
            'abricate': None,
            'quast': None
        }
        
        for file_path, file_info in files.items():
            filename_lower = file_info['name'].lower()
            if 'nanoplot-report.html' in filename_lower:
                key_reports['nanoplot'] = file_path
            elif filename_lower == 'nextflow_report.html':
                key_reports['nextflow_report'] = file_path
            elif filename_lower == 'nextflow_timeline.html':
                key_reports['nextflow_timeline'] = file_path
            elif 'kraken' in filename_lower and file_info['extension'] in {'.txt', '.kreport'}:
                key_reports['kraken'] = file_path
            elif 'checkm' in filename_lower:
                key_reports['checkm'] = file_path
            elif 'abricate' in filename_lower:
                key_reports['abricate'] = file_path
            elif 'report.html' in filename_lower and 'quast' in file_path.lower():
                key_reports['quast'] = file_path
        
        return json({
            'run_id': run_id,
            'stages': stages,
            'key_reports': key_reports,
            'total_files': len(files)
        })
    
    except Exception as e:
        logger.error(f"Error getting run summary: {str(e)}")
        return json({'error': str(e)}, status=500)


@results_bp.route('/<run_id>/pipeline-summary')
@protected
async def get_pipeline_summary(request, run_id):
    """Get aggregated pipeline summary — built from MinIO Silver files."""
    import json as json_module
    import math
    import re
    import os
    from minio import Minio
    from minio.error import S3Error

    # Known genera with pathogenicity info
    KNOWN_PATHOGENS = {
        'Pseudomonas':    ('medium', 'opportunistic',  'Opportunistic pathogen, common in ICU and immunocompromised patients'),
        'Klebsiella':     ('high',   'pathogen',       'Major cause of nosocomial pneumonia, UTI, and sepsis'),
        'Escherichia':    ('medium', 'pathogen',       'Includes pathogenic strains (STEC, UPEC); also commensal'),
        'Salmonella':     ('high',   'pathogen',       'Foodborne pathogen causing typhoid and gastroenteritis'),
        'Staphylococcus': ('high',   'pathogen',       'Causes skin, wound infections; MRSA is multi-drug resistant'),
        'Clostridium':    ('high',   'pathogen',       'Toxin-producing: C. difficile, C. perfringens, botulism'),
        'Acinetobacter':  ('high',   'pathogen',       'Multi-drug resistant nosocomial pathogen; carbapenem resistance'),
        'Enterococcus':   ('medium', 'pathogen',       'Nosocomial infections; VRE strains are a major concern'),
        'Streptococcus':  ('medium', 'pathogen',       'Pneumonia, meningitis, pharyngitis depending on species'),
        'Campylobacter':  ('high',   'pathogen',       'Most common foodborne bacterial pathogen'),
        'Listeria':       ('high',   'pathogen',       'Listeriosis: meningitis, septicemia in immunocompromised'),
        'Vibrio':         ('high',   'pathogen',       'Cholera (V. cholerae), wound infections (V. vulnificus)'),
        'Helicobacter':   ('medium', 'pathogen',       'Gastric ulcers and gastric cancer risk'),
        'Legionella':     ('high',   'pathogen',       "Legionnaires' disease — severe pneumonia"),
        'Mycobacterium':  ('high',   'pathogen',       'Tuberculosis, leprosy, and non-tuberculous mycobacteria'),
        'Enterobacter':   ('medium', 'opportunistic',  'Nosocomial infections; broad-spectrum beta-lactamase producer'),
        'Stenotrophomonas': ('medium', 'opportunistic', 'Intrinsically resistant to many antibiotics; immunocompromised'),
        'Burkholderia':   ('high',   'pathogen',       'B. cepacia in CF patients; B. pseudomallei causes melioidosis'),
        'Bacteroides':    ('low',    'commensal',      'Normal gut flora; rarely causes intra-abdominal infections'),
        'Prevotella':     ('low',    'commensal',      'Oral/gut commensal; occasional periodontal disease'),
        'Fusobacterium':  ('medium', 'pathogen',       'Periodontal disease; associated with colorectal cancer'),
        'Clostridiales':  ('medium', 'environmental',  'Gut microbiome members; some produce toxins'),
        'Firmicutes':     ('low',    'environmental',  'Major gut phylum; largely commensal'),
        'Proteobacteria': ('low',    'environmental',  'Diverse phylum; includes many environmental organisms'),
        'Actinobacteria': ('low',    'environmental',  'Soil bacteria; some produce antibiotics'),
        'Bacteroidetes':  ('low',    'environmental',  'Common gut phylum; largely beneficial'),
    }

    def _assembly_quality_score(n50):
        """Log-scale quality score: N50=1k→20, 10k→60, 100k→80, 1M→100"""
        if not n50 or n50 <= 0:
            return 0
        return min(100, max(0, round(math.log10(n50) * 20 - 20)))

    def _safe_float(s):
        try:
            return float(str(s).replace(',', ''))
        except (TypeError, ValueError):
            return 0.0

    try:
        db_pool = request.app.ctx.db_pool

        # Resolve pipeline_id + sample_name from DB
        try:
            pid_int = int(run_id)
            query = "SELECT pipeline_id, sample_name FROM pipeline_runs WHERE pipeline_id = $1"
            async with db_pool.acquire() as conn:
                row = await conn.fetchrow(query, pid_int)
        except ValueError:
            query = """
                SELECT pipeline_id, sample_name FROM pipeline_runs
                WHERE sample_name = $1 AND status = 'completed'
                ORDER BY pipeline_id DESC LIMIT 1
            """
            async with db_pool.acquire() as conn:
                row = await conn.fetchrow(query, run_id)

        if not row:
            return json({'error': 'Pipeline run not found', 'run_id': run_id}, status=404)

        pipeline_id = row['pipeline_id']
        sample_name = row['sample_name']

        # MinIO client
        minio = Minio(
            os.environ.get('MINIO_ENDPOINT', 'minio:9000'),
            access_key=os.environ['MINIO_ROOT_USER'],
            secret_key=os.environ['MINIO_ROOT_PASSWORD'],
            secure=False,
        )
        prefix = f"{sample_name}/{pipeline_id}/"

        def get_obj(key):
            try:
                r = minio.get_object('genomic-silver', key)
                data = r.read().decode('utf-8', errors='replace')
                r.close()
                return data
            except S3Error:
                return None

        def find_obj(dir_prefix, suffix):
            """Find first MinIO object ending with suffix in a directory prefix."""
            try:
                for obj in minio.list_objects('genomic-silver', prefix=dir_prefix, recursive=True):
                    if obj.object_name.endswith(suffix):
                        return get_obj(obj.object_name)
            except Exception as e:
                logger.warning(f"Error listing MinIO objects at {dir_prefix}: {e}")
            return None

        # ── QC: NanoStats ──────────────────────────────────────────────
        qc = {}
        # Filename may be {sample}_NanoStats.txt or {sample}_1_NanoStats.txt (fasterq-dump adds _1)
        nanostats_raw = (
            get_obj(f"{prefix}01_QC/nanoplot/{sample_name}_NanoStats.txt") or
            get_obj(f"{prefix}01_QC/nanoplot/{sample_name}_1_NanoStats.txt") or
            find_obj(f"{prefix}01_QC/nanoplot/", "_NanoStats.txt")
        )
        if nanostats_raw:
            def ns(pattern):
                m = re.search(pattern, nanostats_raw)
                return float(m.group(1).replace(',', '')) if m else 0
            mean_q = ns(r'Mean read quality:\s+([\d.]+)')
            qc = {
                'reads_count':   int(ns(r'Number of reads:\s+([\d,]+)')),
                'total_bases':   int(ns(r'Total bases:\s+([\d,]+)')),
                'mean_qual':     mean_q,
                'median_qual':   ns(r'Median read quality:\s+([\d.]+)'),
                'mean_length':   int(ns(r'Mean read length:\s+([\d,]+)')),
                'median_length': int(ns(r'Median read length:\s+([\d,]+)')),
                'n50_read':      int(ns(r'Read length N50:\s+([\d,]+)')),
                'quality_score': min(100, round(mean_q * 5)),
            }

        # ── Assembly stats ──────────────────────────────────────────────
        assembly = {}
        asm_raw = (
            get_obj(f"{prefix}03_assembly/{sample_name}_assembly_stats.json") or
            get_obj(f"{prefix}03_assembly/{sample_name}_1_assembly_stats.json") or
            find_obj(f"{prefix}03_assembly/", "_assembly_stats.json")
        )
        if asm_raw:
            try:
                asm_json = json_module.loads(asm_raw)
                n50 = asm_json.get('n50', 0)
                assembly = {
                    'total_length':   asm_json.get('total_length', 0),
                    'contigs':        asm_json.get('num_contigs', 0),
                    'n50':            n50,
                    'n90':            asm_json.get('n90', 0),
                    'largest_contig': asm_json.get('largest_contig', 0),
                    'gc_content':     asm_json.get('gc_content', 0),
                    'quality_score':  _assembly_quality_score(n50),
                }
            except Exception as e:
                logger.warning(f"Failed to parse assembly JSON for {sample_name}: {e}")

        # Fallback: parse txt file (also fills largest_contig if JSON was missing it)
        if not assembly or assembly.get('largest_contig', 0) == 0:
            asm_txt = (
                get_obj(f"{prefix}03_assembly/{sample_name}_assembly_stats.txt") or
                get_obj(f"{prefix}03_assembly/{sample_name}_1_assembly_stats.txt") or
                find_obj(f"{prefix}03_assembly/", "_assembly_stats.txt")
            )
            if asm_txt:
                def av(pat):
                    m = re.search(pat, asm_txt, re.IGNORECASE)
                    return int(m.group(1).replace(',', '')) if m else 0
                lc = (av(r'Longest[_ ]contig[^:]*:\s+([\d,]+)') or
                      av(r'Max[_ ]contig[^:]*:\s+([\d,]+)') or
                      av(r'Largest[_ ]contig[^:]*:\s+([\d,]+)'))
                if not assembly:
                    n50 = av(r'N50[^:]*:\s+([\d,]+)')
                    assembly = {
                        'total_length':   av(r'Total[_ ]length[^:]*:\s+([\d,]+)') or av(r'Total[_ ]Length[^:]*:\s+([\d,]+)'),
                        'contigs':        av(r'Number of [Cc]ontigs[^:]*:\s+([\d,]+)') or av(r'Contigs[^:]*:\s+([\d,]+)'),
                        'n50':            n50,
                        'n90':            av(r'N90[^:]*:\s+([\d,]+)'),
                        'largest_contig': lc,
                        'gc_content':     0,
                        'quality_score':  _assembly_quality_score(n50),
                    }
                elif lc:
                    assembly['largest_contig'] = lc

        # ── MAGs: CheckM ───────────────────────────────────────────────
        mags = {
            'bins': [], 'total': 0, 'total_bins': 0,
            'high_quality': 0, 'medium_quality': 0, 'low_quality': 0,
        }
        checkm_raw = (
            get_obj(f"{prefix}05_quality/metabat2/{sample_name}_metabat2_checkm_summary.tsv") or
            get_obj(f"{prefix}05_quality/metabat2/{sample_name}_1_metabat2_checkm_summary.tsv") or
            find_obj(f"{prefix}05_quality/metabat2/", "_metabat2_checkm_summary.tsv")
        )
        if checkm_raw:
            bins = []
            for line in checkm_raw.strip().split('\n')[1:]:
                parts = line.split('\t')
                if len(parts) < 13:
                    continue
                try:
                    comp = float(parts[11])
                    cont = float(parts[12])
                    # Skip special/degenerate bins (lowDepth, unbinned, tooShort)
                    bin_name = parts[0].strip()
                    if any(x in bin_name.lower() for x in ('lowdepth', 'unbinned', 'tooshort')):
                        continue
                    # Also skip biologically implausible entries
                    if cont > 100 or comp < 0:
                        continue
                    strain_het = _safe_float(parts[13]) if len(parts) > 13 else 0.0
                    grade = ('high'   if comp >= 90 and cont <= 5  else
                             'medium' if comp >= 50 and cont <= 10 else 'low')
                    bins.append({
                        'bin_id':              bin_name,
                        'name':                bin_name,
                        'lineage':             parts[1],
                        'completeness':        round(comp, 2),
                        'contamination':       round(cont, 2),
                        'strain_heterogeneity': round(strain_het, 2),
                        'quality':             grade,
                    })
                    if grade == 'high':
                        mags['high_quality'] += 1
                    elif grade == 'medium':
                        mags['medium_quality'] += 1
                    else:
                        mags['low_quality'] += 1
                except (ValueError, IndexError) as e:
                    logger.warning(f"Skipping malformed CheckM line for {sample_name}: {e}")
            mags['bins']       = sorted(bins, key=lambda x: -x['completeness'])[:20]
            mags['total']      = len(bins)
            mags['total_bins'] = len(bins)

        # ── Taxonomy: aggregate across all per-bin kraken2 reports ─────
        genus_counts = {}
        phylum_counts = {}
        kraken_objs = minio.list_objects('genomic-silver', prefix=f"{prefix}06_kraken2/", recursive=False)
        for obj in kraken_objs:
            if not obj.object_name.endswith('_kraken2_report.txt'):
                continue
            raw = get_obj(obj.object_name)
            if not raw:
                continue
            for line in raw.strip().split('\n'):
                parts = line.strip().split('\t')
                if len(parts) < 6:
                    continue
                try:
                    pct  = float(parts[0])
                    rank = parts[3].strip()
                    name = parts[5].strip()
                except (ValueError, IndexError):
                    continue
                if pct < 1.0 or not name:
                    continue
                if rank == 'G':
                    genus_counts[name] = genus_counts.get(name, 0) + pct
                elif rank == 'P':
                    phylum_counts[name] = phylum_counts.get(name, 0) + pct

        pool = genus_counts if genus_counts else phylum_counts
        total_abund = sum(pool.values()) or 1
        organisms = [
            {'name': k, 'abundance': round(v / total_abund * 100, 1)}
            for k, v in sorted(pool.items(), key=lambda x: -x[1])[:15]
        ]

        # Enrich organisms → species entries with pathogenicity info
        species = []
        risk_assessment = {'high': 0, 'medium': 0, 'low': 0}
        for org in organisms:
            genus = org['name'].split()[0]
            risk, patho, clinical = KNOWN_PATHOGENS.get(
                genus, ('low', 'environmental', 'No specific clinical relevance identified'))
            species.append({
                'name':              org['name'],
                'abundance':         org['abundance'],
                'bin':               None,
                'risk_level':        risk,
                'pathogenicity':     patho,
                'clinical_relevance': clinical,
            })
            risk_assessment[risk] += 1

        taxonomy = {
            'organisms':       organisms,
            'species':         species,
            'risk_assessment': risk_assessment,
        }

        # ── AMR: ABRicate ──────────────────────────────────────────────
        amr = {'total_genes': 0, 'categories': [], 'genes': [],
               'high_risk_genes': 0, 'medium_risk_genes': 0}
        cats = {}
        gene_list = []
        abricate_objs = minio.list_objects('genomic-silver', prefix=f"{prefix}07_amr/abricate/", recursive=True)
        for obj in abricate_objs:
            raw = get_obj(obj.object_name)
            if not raw:
                continue
            for line in raw.strip().split('\n')[1:]:
                if not line.strip():
                    continue
                parts = line.split('\t')
                if len(parts) < 15:
                    continue
                gene       = parts[5].strip()
                resistance = parts[14].strip()
                pct_cov    = _safe_float(parts[9])
                pct_id     = _safe_float(parts[10])
                if not resistance or resistance in ('.', ''):
                    continue
                for cat in resistance.split(';'):
                    cat = cat.strip()
                    if cat:
                        cats[cat] = cats.get(cat, 0) + 1
                        amr['total_genes'] += 1
                if gene and gene not in [g['gene'] for g in gene_list[-50:]]:
                    antibiotic_class = resistance.split(';')[0].strip() if resistance else 'Unknown'
                    gene_list.append({
                        'gene':            gene,
                        'resistance':      resistance,
                        'antibiotic_class': antibiotic_class,
                        'mechanism':       'Resistance gene',
                        'coverage':        round(pct_cov, 1),
                        'identity':        round(pct_id, 1),
                    })
                    if pct_id >= 90:
                        amr['high_risk_genes'] += 1
                    elif pct_id >= 70:
                        amr['medium_risk_genes'] += 1

        amr['categories'] = [
            {'name': k, 'count': v}
            for k, v in sorted(cats.items(), key=lambda x: -x[1])[:12]
        ]
        amr['genes'] = gene_list[:30]

        # ── Risk scores ────────────────────────────────────────────────
        total_genes = amr['total_genes']
        amr_risk = min(100, round(total_genes / 5))
        qual_score = qc.get('quality_score', 0)

        return json({
            'sample_name':    sample_name,
            'pipeline_id':    pipeline_id,
            'status':         'completed',
            'quality_score':  qual_score,
            'amr_risk_score': amr_risk,
            'qc':       qc,
            'assembly': assembly,
            'mags':     mags,
            'amr':      amr,
            'taxonomy': taxonomy,
        })

    except Exception as e:
        logger.error(f"Error getting pipeline summary for {run_id}: {str(e)}", exc_info=True)
        return json({'error': str(e)}, status=500)


@results_bp.route('/<run_id>/pipeline-qc')
@protected
async def get_qc_metrics(request, run_id):
    """Get QC metrics only"""
    try:
        summary_file = RESULTS_DIR / run_id / '00_summary' / f'{run_id}_summary.json'
        
        if not summary_file.exists():
            return json({'error': 'Summary not found'}, status=404)
        
        import json as json_module
        with open(summary_file) as f:
            summary_data = json_module.load(f)
        
        return json(summary_data.get('qc', {}))
    
    except Exception as e:
        logger.error(f"Error getting QC metrics: {str(e)}")
        return json({'error': str(e)}, status=500)


@results_bp.route('/<run_id>/pipeline-assembly')
@protected
async def get_assembly_metrics(request, run_id):
    """Get assembly metrics only"""
    try:
        summary_file = RESULTS_DIR / run_id / '00_summary' / f'{run_id}_summary.json'
        
        if not summary_file.exists():
            return json({'error': 'Summary not found'}, status=404)
        
        import json as json_module
        with open(summary_file) as f:
            summary_data = json_module.load(f)
        
        return json(summary_data.get('assembly', {}))
    
    except Exception as e:
        logger.error(f"Error getting assembly metrics: {str(e)}")
        return json({'error': str(e)}, status=500)


@results_bp.route('/<run_id>/pipeline-amr')
@protected
async def get_amr_analysis(request, run_id):
    """Get AMR analysis only"""
    try:
        summary_file = RESULTS_DIR / run_id / '00_summary' / f'{run_id}_summary.json'
        
        if not summary_file.exists():
            return json({'error': 'Summary not found'}, status=404)
        
        import json as json_module
        with open(summary_file) as f:
            summary_data = json_module.load(f)
        
        return json(summary_data.get('amr', {}))
    
    except Exception as e:
        logger.error(f"Error getting AMR analysis: {str(e)}")
        return json({'error': str(e)}, status=500)


@results_bp.route('/<run_id>/pipeline-taxonomy')
@protected
async def get_taxonomy(request, run_id):
    """Get taxonomy results only"""
    try:
        summary_file = RESULTS_DIR / run_id / '00_summary' / f'{run_id}_summary.json'
        
        if not summary_file.exists():
            return json({'error': 'Summary not found'}, status=404)
        
        import json as json_module
        with open(summary_file) as f:
            summary_data = json_module.load(f)
        
        return json(summary_data.get('taxonomy', {}))
    
    except Exception as e:
        logger.error(f"Error getting taxonomy: {str(e)}")
        return json({'error': str(e)}, status=500)


@results_bp.route('/<run_id>/pipeline-mags')
@protected
async def get_mags_quality(request, run_id):
    """Get MAG quality assessment only"""
    try:
        summary_file = RESULTS_DIR / run_id / '00_summary' / f'{run_id}_summary.json'
        
        if not summary_file.exists():
            return json({'error': 'Summary not found'}, status=404)
        
        import json as json_module
        with open(summary_file) as f:
            summary_data = json_module.load(f)
        
        return json(summary_data.get('mags', {}))
    
    except Exception as e:
        logger.error(f"Error getting MAGs: {str(e)}")
        return json({'error': str(e)}, status=500)
