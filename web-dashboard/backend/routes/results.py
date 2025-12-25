# Pipeline Results API Routes
# Handles viewing and downloading of pipeline execution results

from sanic import Blueprint, response
from sanic.response import json, file, html
from pathlib import Path
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

results_bp = Blueprint('results', url_prefix='/api/pipeline/results')

# Results directory configuration
RESULTS_DIR = Path('/results')  # Mounted from host at /home/nicolaedrabcinski/upgrade/results

# File types that can be viewed directly in browser
VIEWABLE_EXTENSIONS = {'.html', '.txt', '.log', '.tsv', '.csv', '.json', '.xml', '.gff', '.kreport'}
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.svg', '.gif'}
PDF_EXTENSIONS = {'.pdf'}


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
async def list_run_files(request, run_id):
    """List all files in a specific run"""
    try:
        run_path = RESULTS_DIR / run_id
        
        if not run_path.exists():
            return json({'error': 'Run not found'}, status=404)
        
        files = scan_run_directory(run_path)
        
        return json({
            'run_id': run_id,
            'files': files,
            'count': len(files)
        })
    
    except Exception as e:
        logger.error(f"Error listing run files: {str(e)}")
        return json({'error': str(e)}, status=500)


@results_bp.route('/<run_id>/view')
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
async def get_pipeline_summary(request, run_id):
    """Get aggregated pipeline summary JSON"""
    try:
        run_dir = RESULTS_DIR / run_id
        
        if not run_dir.exists():
            return json({
                'error': 'Run directory not found',
                'run_id': run_id
            }, status=404)
        
        # Try multiple locations for summary file
        summary_file = None
        
        # 1. Standard location: 00_summary/{run_id}_summary.json
        candidate = run_dir / '00_summary' / f'{run_id}_summary.json'
        if candidate.exists():
            summary_file = candidate
        
        # 2. Any summary.json in 00_summary/
        if not summary_file:
            summary_dir = run_dir / '00_summary'
            if summary_dir.exists():
                for f in summary_dir.glob('*_summary.json'):
                    summary_file = f
                    break
        
        # 3. Root directory: {run_id}_summary.json
        if not summary_file:
            candidate = run_dir / f'{run_id}_summary.json'
            if candidate.exists():
                summary_file = candidate
        
        if not summary_file:
            return json({
                'error': 'Summary not found. Run pipeline with summary generation enabled.',
                'run_id': run_id,
                'hint': f'Looking for *_summary.json in {run_dir}/00_summary/'
            }, status=404)
        
        # Read and return JSON
        import json as json_module
        with open(summary_file) as f:
            summary_data = json_module.load(f)
        
        return json(summary_data)
    
    except Exception as e:
        logger.error(f"Error getting pipeline summary for {run_id}: {str(e)}")
        return json({'error': str(e)}, status=500)


@results_bp.route('/<run_id>/pipeline-qc')
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
