"""
API routes for samples and genomics data
"""
from sanic import Blueprint, response
from sanic.log import logger
from datetime import datetime, timedelta, date
from auth import protected


def serialize(obj):
    """Recursively make a dict/list JSON-safe (convert datetime, date, etc.)."""
    if isinstance(obj, dict):
        return {k: serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [serialize(v) for v in obj]
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    return obj

samples_bp = Blueprint('samples', url_prefix='/api/samples')


@samples_bp.route('/map', methods=['GET'])
@protected
async def get_samples_for_map(request):
    """
    Get samples with location data for map visualization.
    Query params:
      - dateRange: all, 7days, 30days, 90days
      - sampleType: all, nanopore, illumina, pacbio
      - hasAMR: true/false
    """
    try:
        date_range = request.args.get('dateRange', 'all')
        sample_type = request.args.get('sampleType', 'all')
        has_amr = request.args.get('hasAMR', 'false').lower() == 'true'

        where_clauses = ["l.latitude IS NOT NULL", "l.longitude IS NOT NULL"]
        params = []

        if date_range != 'all':
            days = {'7days': 7, '30days': 30, '90days': 90}.get(date_range, 0)
            if days > 0:
                cutoff_date = datetime.now() - timedelta(days=days)
                where_clauses.append(f"s.collection_date >= ${len(params) + 1}")
                params.append(cutoff_date)

        if sample_type != 'all':
            where_clauses.append(f"s.sequencing_platform = ${len(params) + 1}")
            params.append(sample_type)

        if has_amr:
            where_clauses.append(
                "EXISTS (SELECT 1 FROM resistance_genes rg WHERE rg.sample_id = s.sample_id)"
            )

        where_sql = " AND ".join(where_clauses)

        pool = request.app.ctx.db_pool
        async with pool.acquire() as conn:
            query = f"""
                SELECT
                    s.sample_id,
                    s.sample_code,
                    l.latitude,
                    l.longitude,
                    l.location_name,
                    l.city,
                    l.country,
                    s.collection_date,
                    s.sample_type,
                    s.sequencing_platform,
                    COUNT(DISTINCT rg.rg_id)          AS amr_genes_count,
                    COUNT(DISTINCT rg.gene_name)       AS unique_amr_genes,
                    COUNT(DISTINCT dorg.organism_name)  AS pathogens_count,
                    array_agg(
                        DISTINCT jsonb_build_object(
                            'pipeline_id', pr.pipeline_id,
                            'status', pr.status
                        )
                    ) FILTER (WHERE pr.pipeline_id IS NOT NULL) AS pipeline_runs
                FROM samples s
                LEFT JOIN locations l         ON s.location_id = l.location_id
                LEFT JOIN resistance_genes rg ON s.sample_id   = rg.sample_id
                LEFT JOIN detected_organisms dorg ON s.sample_id = dorg.sample_id
                LEFT JOIN pipeline_runs pr    ON s.sample_id   = pr.sample_id
                WHERE {where_sql}
                GROUP BY s.sample_id, l.latitude, l.longitude,
                         l.location_name, l.city, l.country
                ORDER BY s.collection_date DESC NULLS LAST
                LIMIT 1000
            """
            samples = await conn.fetch(query, *params)

            samples_list = []
            for row in samples:
                d = dict(row)
                if d.get('collection_date'):
                    d['collection_date'] = d['collection_date'].isoformat()
                samples_list.append(d)

            stats = await conn.fetchrow(f"""
                SELECT
                    COUNT(DISTINCT s.sample_id)       AS total_samples,
                    COUNT(DISTINCT rg.rg_id)          AS total_amr_genes,
                    COUNT(DISTINCT dorg.organism_name) AS unique_pathogens
                FROM samples s
                LEFT JOIN locations l              ON s.location_id = l.location_id
                LEFT JOIN resistance_genes rg      ON s.sample_id   = rg.sample_id
                LEFT JOIN detected_organisms dorg  ON s.sample_id   = dorg.sample_id
                WHERE {where_sql}
            """, *params)

            return response.json({
                'samples': samples_list,
                'stats': dict(stats) if stats else {
                    'total_samples': 0,
                    'total_amr_genes': 0,
                    'unique_pathogens': 0,
                },
            })

    except Exception as e:
        logger.error(f"Error fetching samples for map: {e}")
        return response.json({
            'error': str(e),
            'samples': [],
            'stats': {'total_samples': 0, 'total_amr_genes': 0, 'unique_pathogens': 0},
        }, status=500)


@samples_bp.route('/<sample_id:int>', methods=['GET'])
@protected
async def get_sample_details(request, sample_id):
    """Get detailed information about a specific sample"""
    try:
        pool = request.app.ctx.db_pool
        async with pool.acquire() as conn:
            sample = await conn.fetchrow(
                "SELECT * FROM samples WHERE sample_id = $1", sample_id
            )
            if not sample:
                return response.json({'error': 'Sample not found'}, status=404)

            amr_results = await conn.fetch("""
                SELECT gene_name, predicted_resistance, resistance_mechanism,
                       coverage, identity, detection_tool
                FROM resistance_genes
                WHERE sample_id = $1
                ORDER BY coverage DESC NULLS LAST
            """, sample_id)

            taxonomy_results = await conn.fetch("""
                SELECT organism_name AS species,
                       scientific_name,
                       taxonomy_rank,
                       abundance,
                       read_count
                FROM detected_organisms
                WHERE sample_id = $1
                ORDER BY abundance DESC NULLS LAST
                LIMIT 20
            """, sample_id)

            pipeline_runs = await conn.fetch("""
                SELECT pipeline_id, status,
                       started_at AS start_time,
                       completed_at AS end_time
                FROM pipeline_runs
                WHERE sample_id = $1
                ORDER BY started_at DESC NULLS LAST
            """, sample_id)

            sample_dict = dict(sample)
            if sample_dict.get('collection_date'):
                sample_dict['collection_date'] = sample_dict['collection_date'].isoformat()

            return response.json(serialize({
                'sample': sample_dict,
                'amr_results': [dict(r) for r in amr_results],
                'taxonomy': [dict(t) for t in taxonomy_results],
                'pipeline_runs': [dict(p) for p in pipeline_runs],
            }))

    except Exception as e:
        logger.error(f"Error fetching sample {sample_id}: {e}")
        return response.json({'error': str(e)}, status=500)


@samples_bp.route('/stats', methods=['GET'])
@protected
async def get_global_stats(request):
    """Get global statistics for dashboard"""
    try:
        pool = request.app.ctx.db_pool
        async with pool.acquire() as conn:
            stats = await conn.fetchrow("""
                SELECT
                    COUNT(DISTINCT s.sample_id) AS total_samples,
                    COUNT(DISTINCT CASE WHEN pr.status = 'completed'
                          THEN pr.pipeline_id END)   AS completed_pipelines,
                    COUNT(DISTINCT rg.gene_name)      AS unique_amr_genes,
                    COUNT(DISTINCT dorg.organism_name)  AS unique_species
                FROM samples s
                LEFT JOIN pipeline_runs pr      ON s.sample_id = pr.sample_id
                LEFT JOIN resistance_genes rg   ON s.sample_id = rg.sample_id
                LEFT JOIN detected_organisms dorg ON s.sample_id = dorg.sample_id
            """)

            activity = await conn.fetch("""
                SELECT
                    s.sample_code,
                    pr.status,
                    pr.started_at AS start_time,
                    COUNT(rg.rg_id) AS amr_count
                FROM samples s
                JOIN pipeline_runs pr     ON s.sample_id = pr.sample_id
                LEFT JOIN resistance_genes rg ON s.sample_id = rg.sample_id
                WHERE pr.started_at >= NOW() - INTERVAL '7 days'
                GROUP BY s.sample_code, pr.status, pr.started_at
                ORDER BY pr.started_at DESC NULLS LAST
                LIMIT 10
            """)

            return response.json(serialize({
                'stats': dict(stats) if stats else {},
                'recent_activity': [dict(row) for row in activity],
            }))

    except Exception as e:
        logger.error(f"Error fetching global stats: {e}")
        return response.json({'error': str(e)}, status=500)
