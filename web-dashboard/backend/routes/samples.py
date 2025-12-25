"""
API routes for samples and genomics data
"""
from sanic import Blueprint, response
from sanic.log import logger
import psycopg2
from psycopg2.extras import RealDictCursor
from config import config
from datetime import datetime, timedelta

samples_bp = Blueprint('samples', url_prefix='/api/samples')

def get_db_connection():
    """Create PostgreSQL connection"""
    return psycopg2.connect(
        host=config.POSTGRES_HOST,
        port=config.POSTGRES_PORT,
        database=config.POSTGRES_DB,
        user=config.POSTGRES_USER,
        password=config.POSTGRES_PASSWORD
    )

@samples_bp.route('/map', methods=['GET'])
async def get_samples_for_map(request):
    """
    Get samples with location data for map visualization
    Query params:
      - dateRange: all, 7days, 30days, 90days
      - sampleType: all, nanopore, illumina, pacbio
      - hasAMR: true/false
    """
    try:
        # Parse filters
        date_range = request.args.get('dateRange', 'all')
        sample_type = request.args.get('sampleType', 'all')
        has_amr = request.args.get('hasAMR', 'false').lower() == 'true'
        
        # Build WHERE clause
        where_clauses = ["s.latitude IS NOT NULL", "s.longitude IS NOT NULL"]
        params = []
        
        # Date filter
        if date_range != 'all':
            days = {'7days': 7, '30days': 30, '90days': 90}.get(date_range, 0)
            if days > 0:
                cutoff_date = datetime.now() - timedelta(days=days)
                where_clauses.append("s.collection_date >= %s")
                params.append(cutoff_date)
        
        # Sample type filter
        if sample_type != 'all':
            where_clauses.append("s.sequencing_platform = %s")
            params.append(sample_type)
        
        # AMR filter
        if has_amr:
            where_clauses.append("ar.amr_genes_count > 0")
        
        where_sql = " AND ".join(where_clauses)
        
        conn = get_db_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Get samples with aggregated data
                query = f"""
                    SELECT 
                        s.sample_id,
                        s.sample_code,
                        s.latitude,
                        s.longitude,
                        s.location_name,
                        s.city,
                        s.country,
                        s.collection_date,
                        s.sample_type,
                        s.sequencing_platform,
                        COALESCE(ar.amr_genes_count, 0) as amr_genes_count,
                        COALESCE(ar.unique_amr_genes, 0) as unique_amr_genes,
                        COALESCE(t.pathogens_count, 0) as pathogens_count,
                        array_agg(
                            DISTINCT jsonb_build_object(
                                'pipeline_id', pr.pipeline_id,
                                'status', pr.status
                            )
                        ) FILTER (WHERE pr.pipeline_id IS NOT NULL) as pipeline_runs
                    FROM samples s
                    LEFT JOIN LATERAL (
                        SELECT 
                            0 as amr_genes_count,
                            0 as unique_amr_genes
                    ) ar ON true
                    LEFT JOIN LATERAL (
                        SELECT 
                            0 as pathogens_count
                    ) t ON true
                    LEFT JOIN (
                        SELECT 
                            sample_id,
                            COUNT(*) as amr_genes_count_disabled,
                            COUNT(DISTINCT gene_name) as unique_amr_genes_disabled
                        FROM abricate_results
                        WHERE FALSE
                        GROUP BY sample_id
                    ) ar_disabled ON FALSE
                    LEFT JOIN (
                        SELECT 
                            sample_id,
                            COUNT(DISTINCT species) as pathogens_count_disabled
                        FROM taxonomy_results
                        WHERE FALSE AND abundance > 0.01
                        GROUP BY sample_id
                    ) tr_disabled ON FALSE
                    LEFT JOIN pipeline_runs pr ON s.sample_id = pr.sample_id
                    WHERE {where_sql}
                    GROUP BY s.sample_id, ar.amr_genes_count, ar.unique_amr_genes, t.pathogens_count
                    ORDER BY s.collection_date DESC
                    LIMIT 1000
                """
                
                cur.execute(query, params)
                samples = cur.fetchall()
                
                # Convert date objects to strings
                for sample in samples:
                    if 'collection_date' in sample and sample['collection_date']:
                        sample['collection_date'] = sample['collection_date'].isoformat()
                
                # Get overall stats
                stats_query = f"""
                    SELECT 
                        COUNT(DISTINCT s.sample_id) as total_samples,
                        COALESCE(SUM(ar.amr_genes_count), 0) as total_amr_genes,
                        COUNT(DISTINCT t.species) as unique_pathogens
                    FROM samples s
                    LEFT JOIN (
                        SELECT sample_id, COUNT(*) as amr_genes_count
                        FROM abricate_results
                        GROUP BY sample_id
                    ) ar ON s.sample_id = ar.sample_id
                    LEFT JOIN taxonomy_results t ON s.sample_id = t.sample_id
                    WHERE {where_sql}
                """
                
                cur.execute(stats_query, params)
                stats = cur.fetchone()
                
                return response.json({
                    'samples': [dict(s) for s in samples],
                    'stats': dict(stats) if stats else {
                        'total_samples': 0,
                        'total_amr_genes': 0,
                        'unique_pathogens': 0
                    }
                })
                
        finally:
            conn.close()
            
    except Exception as e:
        logger.error(f"Error fetching samples for map: {e}")
        return response.json({
            'error': str(e),
            'samples': [],
            'stats': {'total_samples': 0, 'total_amr_genes': 0, 'unique_pathogens': 0}
        }, status=500)


@samples_bp.route('/<sample_id:int>', methods=['GET'])
async def get_sample_details(request, sample_id):
    """Get detailed information about a specific sample"""
    try:
        conn = get_db_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Get sample info
                cur.execute("""
                    SELECT * FROM samples WHERE sample_id = %s
                """, (sample_id,))
                sample = cur.fetchone()
                
                if not sample:
                    return response.json({'error': 'Sample not found'}, status=404)
                
                # Get AMR results
                cur.execute("""
                    SELECT 
                        gene_name,
                        resistance_class,
                        resistance_mechanism,
                        coverage,
                        identity
                    FROM abricate_results
                    WHERE sample_id = %s
                    ORDER BY coverage DESC
                """, (sample_id,))
                amr_results = cur.fetchall()
                
                # Get taxonomy results
                cur.execute("""
                    SELECT 
                        species,
                        genus,
                        family,
                        abundance,
                        read_count
                    FROM taxonomy_results
                    WHERE sample_id = %s
                    ORDER BY abundance DESC
                    LIMIT 20
                """, (sample_id,))
                taxonomy = cur.fetchall()
                
                # Get pipeline runs
                cur.execute("""
                    SELECT 
                        pipeline_id,
                        status,
                        start_time,
                        end_time,
                        total_reads,
                        genome_bins_count
                    FROM pipeline_runs
                    WHERE sample_id = %s
                    ORDER BY start_time DESC
                """, (sample_id,))
                pipeline_runs = cur.fetchall()
                
                return response.json({
                    'sample': dict(sample),
                    'amr_results': [dict(r) for r in amr_results],
                    'taxonomy': [dict(t) for t in taxonomy],
                    'pipeline_runs': [dict(p) for p in pipeline_runs]
                })
                
        finally:
            conn.close()
            
    except Exception as e:
        logger.error(f"Error fetching sample {sample_id}: {e}")
        return response.json({'error': str(e)}, status=500)


@samples_bp.route('/stats', methods=['GET'])
async def get_global_stats(request):
    """Get global statistics for dashboard"""
    try:
        conn = get_db_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT 
                        COUNT(DISTINCT s.sample_id) as total_samples,
                        COUNT(DISTINCT CASE WHEN pr.status = 'completed' THEN pr.pipeline_id END) as completed_pipelines,
                        COUNT(DISTINCT ar.gene_name) as unique_amr_genes,
                        COUNT(DISTINCT tr.species) as unique_species,
                        SUM(CASE WHEN ar.resistance_class = 'critical' THEN 1 ELSE 0 END) as critical_amr_count
                    FROM samples s
                    LEFT JOIN pipeline_runs pr ON s.sample_id = pr.sample_id
                    LEFT JOIN abricate_results ar ON s.sample_id = ar.sample_id
                    LEFT JOIN taxonomy_results tr ON s.sample_id = tr.sample_id
                """)
                stats = cur.fetchone()
                
                # Get recent activity
                cur.execute("""
                    SELECT 
                        s.sample_code,
                        pr.status,
                        pr.start_time,
                        COUNT(ar.gene_name) as amr_count
                    FROM samples s
                    JOIN pipeline_runs pr ON s.sample_id = pr.sample_id
                    LEFT JOIN abricate_results ar ON s.sample_id = ar.sample_id
                    WHERE pr.start_time >= NOW() - INTERVAL '7 days'
                    GROUP BY s.sample_code, pr.status, pr.start_time
                    ORDER BY pr.start_time DESC
                    LIMIT 10
                """)
                recent_activity = cur.fetchall()
                
                return response.json({
                    'stats': dict(stats) if stats else {},
                    'recent_activity': [dict(a) for a in recent_activity]
                })
                
        finally:
            conn.close()
            
    except Exception as e:
        logger.error(f"Error fetching global stats: {e}")
        return response.json({'error': str(e)}, status=500)
