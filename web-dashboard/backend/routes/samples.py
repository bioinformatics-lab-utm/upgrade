"""
API routes for samples and genomics data
"""
import json

from sanic import Blueprint, response
from sanic.log import logger
from datetime import datetime, timedelta, date
from auth import protected
from authz import current_user_id
from utils.timestamps import to_iso


def serialize(obj):
    """Recursively make a dict/list JSON-safe (convert datetime, date, etc.)."""
    if isinstance(obj, dict):
        return {k: serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [serialize(v) for v in obj]
    if isinstance(obj, (datetime, date)):
        return to_iso(obj)
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

        # Filters shared by the markers and the stat cards. The cards cover all the
        # user's matching samples, like the header's sample count; only the markers
        # need a location (samples imported from SRA usually have none).
        where_clauses = ["s.owner_id = $1"]
        params = [current_user_id(request)]

        if date_range != 'all':
            days = {'7days': 7, '30days': 30, '90days': 90}.get(date_range, 0)
            if days > 0:
                cutoff_date = datetime.now() - timedelta(days=days)
                where_clauses.append(f"s.collection_date >= ${len(params) + 1}")
                params.append(cutoff_date)

        if sample_type in ('nanopore', 'illumina', 'pacbio'):
            # The platform is stored inconsistently: 'nanopore' / 'Oxford Nanopore' in
            # sequencing_platform, or only in sample_type when the platform is empty
            where_clauses.append(
                f"COALESCE(NULLIF(s.sequencing_platform, ''), s.sample_type) ILIKE '%' || ${len(params) + 1} || '%'"
            )
            params.append(sample_type)

        if has_amr:
            where_clauses.append(
                "EXISTS (SELECT 1 FROM resistance_genes rg WHERE rg.sample_id = s.sample_id)"
            )

        where_sql = " AND ".join(where_clauses)
        map_where_sql = where_sql + " AND l.latitude IS NOT NULL AND l.longitude IS NOT NULL"

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
                    s.temperature_celsius,
                    -- distinct genes: a gene found again by a rerun (or on two contigs) counts once
                    COUNT(DISTINCT rg.gene_name)       AS amr_genes_count,
                    COUNT(DISTINCT rg.gene_name)       AS unique_amr_genes,
                    -- genera classified as (opportunistic) pathogens, as on the results page
                    COUNT(DISTINCT dorg.organism_name) FILTER (
                        WHERE dorg.risk_level IN ('high', 'medium')
                    )                                   AS pathogens_count,
                    -- asyncpg returns json as text; decoded below
                    COALESCE(
                        jsonb_agg(DISTINCT jsonb_build_object(
                            'pipeline_id', pr.pipeline_id,
                            'status', pr.status,
                            'started_at', pr.started_at,
                            'completed_at', pr.completed_at
                        )) FILTER (WHERE pr.pipeline_id IS NOT NULL),
                        '[]'::jsonb
                    )::text AS pipeline_runs
                FROM samples s
                LEFT JOIN locations l         ON s.location_id = l.location_id
                LEFT JOIN resistance_genes rg ON s.sample_id   = rg.sample_id
                LEFT JOIN detected_organisms dorg ON s.sample_id = dorg.sample_id
                LEFT JOIN pipeline_runs pr    ON s.sample_id   = pr.sample_id
                WHERE {map_where_sql}
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
                # Newest run first; json timestamps are naive UTC like the table's
                d['pipeline_runs'] = sorted(
                    json.loads(d['pipeline_runs'] or '[]'),
                    key=lambda run: run['pipeline_id'], reverse=True
                )
                for run in d['pipeline_runs']:
                    for key in ('started_at', 'completed_at'):
                        if run.get(key) and not run[key].endswith(('Z', '+00:00')):
                            run[key] += '+00:00'
                for key in ('latitude', 'longitude', 'temperature_celsius'):
                    if d.get(key) is not None:
                        d[key] = float(d[key])
                samples_list.append(d)

            stats = await conn.fetchrow(f"""
                SELECT
                    COUNT(DISTINCT s.sample_id)       AS total_samples,
                    COUNT(DISTINCT s.sample_id) FILTER (
                        WHERE l.latitude IS NOT NULL AND l.longitude IS NOT NULL
                    )                                 AS samples_on_map,
                    COUNT(DISTINCT s.sample_id::text || ':' || rg.gene_name) AS total_amr_genes,
                    COUNT(DISTINCT dorg.organism_name) FILTER (
                        WHERE dorg.risk_level IN ('high', 'medium')
                    )                                  AS unique_pathogens
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
                    'samples_on_map': 0,
                    'total_amr_genes': 0,
                    'unique_pathogens': 0,
                },
            })

    except Exception as e:
        logger.error(f"Error fetching samples for map: {e}")
        return response.json({
            'error': str(e),
            'samples': [],
            'stats': {'total_samples': 0, 'samples_on_map': 0, 'total_amr_genes': 0, 'unique_pathogens': 0},
        }, status=500)


@samples_bp.route('/locations', methods=['GET'])
@protected
async def list_locations(request):
    """Cities a sample can be assigned to (the map plots samples at these coordinates)."""
    try:
        async with request.app.ctx.db_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT location_id, city, country, latitude, longitude
                FROM locations
                WHERE is_active AND city IS NOT NULL
                  AND latitude IS NOT NULL AND longitude IS NOT NULL
                ORDER BY country, city
            """)
        return response.json({
            'locations': [
                {
                    'location_id': r['location_id'],
                    'city': r['city'],
                    'country': r['country'],
                    'latitude': float(r['latitude']),
                    'longitude': float(r['longitude']),
                }
                for r in rows
            ]
        })
    except Exception as e:
        logger.error(f"Error listing locations: {e}")
        return response.json({'error': 'Failed to load locations', 'locations': []}, status=500)


@samples_bp.route('/<sample_id:int>', methods=['GET'])
@protected
async def get_sample_details(request, sample_id):
    """Get detailed information about a specific sample"""
    try:
        pool = request.app.ctx.db_pool
        async with pool.acquire() as conn:
            sample = await conn.fetchrow(
                """
                SELECT s.*,
                       l.location_name, l.city AS location_city, l.country AS location_country,
                       l.latitude AS location_latitude, l.longitude AS location_longitude
                FROM samples s
                LEFT JOIN locations l ON l.location_id = s.location_id
                WHERE s.sample_id = $1 AND s.owner_id = $2
                """,
                sample_id, current_user_id(request)
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
    """Get dashboard statistics for the current user's samples"""
    try:
        user_id = current_user_id(request)
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
                WHERE s.owner_id = $1
            """, user_id)

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
                  AND s.owner_id = $1
                GROUP BY s.sample_code, pr.status, pr.started_at
                ORDER BY pr.started_at DESC NULLS LAST
                LIMIT 10
            """, user_id)

            return response.json(serialize({
                'stats': dict(stats) if stats else {},
                'recent_activity': [dict(row) for row in activity],
            }))

    except Exception as e:
        logger.error(f"Error fetching global stats: {e}")
        return response.json({'error': str(e)}, status=500)


@samples_bp.route('/<sample_id:int>', methods=['DELETE'])
@protected
async def delete_sample(request, sample_id: int):
    """
    Delete one of the user's samples with all its pipeline runs, results and
    files (MinIO bronze/silver/gold, local results). It disappears from the map,
    the results list and every count. Runs that are queued or running must be
    stopped first.

    Response:
        {"success": true, "sample_code": "...", "runs_deleted": 2,
         "objects_removed": 70, "storage_errors": 0}
    """
    from minio_helper import get_minio_client
    from services.sample_deletion import delete_sample as delete_sample_everywhere, SampleNotFound, SampleHasActiveRuns

    try:
        result = await delete_sample_everywhere(
            request.app.ctx.db_pool, get_minio_client().client, current_user_id(request), sample_id
        )
        return response.json({'success': True, **result})
    except SampleNotFound:
        return response.json({'success': False, 'error': 'Sample not found'}, status=404)
    except SampleHasActiveRuns as e:
        return response.json({
            'success': False,
            'error': 'This sample has a pipeline that is queued or running. Stop it before deleting the sample.',
            'pipeline_ids': e.pipeline_ids,
        }, status=409)
    except Exception as e:
        logger.error(f"Error deleting sample {sample_id}: {e}", exc_info=True)
        return response.json({'success': False, 'error': 'Internal server error'}, status=500)
