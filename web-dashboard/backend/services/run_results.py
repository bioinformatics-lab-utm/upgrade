"""
AMR genes and taxonomy of a pipeline run, read from its Nextflow outputs in the
MinIO Silver layer (genomic-silver/<sample_name>/<pipeline_id>/...).

One implementation for every place that shows these results: the results page
and its PDF (routes/results.py), the stored rows that feed the map and the
notification emails (resistance_genes / detected_organisms, written by the
worker and by scripts/backfill_run_results.py).
"""
import asyncio
from typing import Dict, List, Optional

from services.kraken_abundance import sample_genus_abundance

SILVER = 'genomic-silver'

# Genus (or higher taxon) -> (risk level, pathogenicity, clinical relevance)
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
UNKNOWN_TAXON = ('low', 'environmental', 'No specific clinical relevance identified')


def classify(name: str):
    """(risk level, pathogenicity, clinical relevance) of a genus."""
    return KNOWN_PATHOGENS.get(name.split()[0], UNKNOWN_TAXON)


def _list(minio, prefix: str, recursive: bool = True) -> List[str]:
    return [o.object_name for o in minio.list_objects(SILVER, prefix=prefix, recursive=recursive)]


def _read(minio, key: str) -> Optional[str]:
    try:
        response = minio.get_object(SILVER, key)
    except Exception:
        return None
    try:
        return response.read().decode('utf-8', errors='replace')
    finally:
        response.close()
        response.release_conn()


# ── AMR: ABRicate ────────────────────────────────────────────────────────────

def parse_abricate_tables(tables: List[str]) -> List[Dict]:
    """
    Resistance genes from ABRicate per-hit tables (*.tab), best hit per gene.

    Columns: #FILE SEQUENCE START END STRAND GENE COVERAGE COVERAGE_MAP GAPS
             %COVERAGE %IDENTITY DATABASE ACCESSION PRODUCT RESISTANCE
    The abricate --summary matrices (*_summary.txt) are not gene tables.
    """
    genes: Dict[str, Dict] = {}
    for raw in tables:
        if not raw or not raw.startswith('#FILE\tSEQUENCE'):
            continue
        for line in raw.strip().split('\n')[1:]:
            parts = line.split('\t')
            if len(parts) < 15:
                continue
            gene, resistance = parts[5].strip(), parts[14].strip()
            try:
                coverage, identity = float(parts[9]), float(parts[10])
            except ValueError:
                continue
            if not gene or resistance in ('', '.'):
                continue
            known = genes.get(gene)
            # The same gene can be hit on several contigs/bins: keep the best hit
            if known and (known['identity'], known['coverage']) >= (round(identity, 1), round(coverage, 1)):
                continue
            genes[gene] = {
                'gene':             gene,
                'resistance':       resistance,
                'antibiotic_class': resistance.split(';')[0].strip(),
                'mechanism':        parts[13].strip() or 'Resistance gene',
                'database':         parts[11].strip(),
                'accession':        parts[12].strip(),
                'coverage':         round(coverage, 1),
                'identity':         round(identity, 1),
                # Same rule as nextflow/bin/generate_summary.py
                'risk_level':       'high' if identity >= 90 else 'moderate',
            }
    return sorted(genes.values(), key=lambda g: (g['risk_level'] != 'high', -g['identity'], g['gene']))


def run_amr(minio, prefix: str) -> Dict:
    keys = [k for k in _list(minio, f"{prefix}07_amr/abricate/") if k.endswith('.tab')]
    genes = parse_abricate_tables([_read(minio, k) for k in keys])
    categories: Dict[str, int] = {}
    for g in genes:
        for cat in g['resistance'].split(';'):
            cat = cat.strip()
            if cat:
                categories[cat] = categories.get(cat, 0) + 1
    high = sum(1 for g in genes if g['risk_level'] == 'high')
    return {
        'genes':             genes,
        'total_genes':       len(genes),
        'high_risk_genes':   high,
        'medium_risk_genes': len(genes) - high,
        'categories':        [{'name': k, 'count': v} for k, v in sorted(categories.items(), key=lambda x: -x[1])[:12]],
        # 0-10, same formula as nextflow/bin/generate_summary.py
        'risk_score':        round(min(10, high * 0.5 + (len(genes) - high) * 0.2), 1),
    }


# ── Taxonomy: Kraken2 ────────────────────────────────────────────────────────

def _stream_lines(response, chunk_size: int = 1 << 20):
    """Lines of a MinIO object without loading it whole (outputs can be ~100 MB)."""
    pending = b''
    for chunk in response.stream(chunk_size):
        pending += chunk
        *lines, pending = pending.split(b'\n')
        for line in lines:
            yield line.decode('utf-8', errors='replace')
    if pending:
        yield pending.decode('utf-8', errors='replace')


def _length_weighted(minio, kraken_keys: List[str]) -> Optional[Dict]:
    names = set(kraken_keys)
    pairs = sorted(
        (k, k[:-len('_kraken2_report.txt')] + '_kraken2_output.txt')
        for k in names if k.endswith('_kraken2_report.txt')
    )
    pairs = [(report, output) for report, output in pairs if output in names]
    if not pairs:
        return None

    def bins():
        for report_key, output_key in pairs:
            report_text = _read(minio, report_key) or ''
            response = minio.get_object(SILVER, output_key)
            try:
                yield report_text, _stream_lines(response)
            finally:
                response.close()
                response.release_conn()

    return sample_genus_abundance(bins())


def _bin_report_average(minio, kraken_keys: List[str], top: int = 15) -> List[Dict]:
    """Older runs kept only the per-bin reports: average the bins' genus percentages."""
    genus_pct: Dict[str, float] = {}
    phylum_pct: Dict[str, float] = {}
    for key in kraken_keys:
        if not key.endswith('_kraken2_report.txt'):
            continue
        for line in (_read(minio, key) or '').strip().split('\n'):
            parts = line.strip().split('\t')
            if len(parts) < 6:
                continue
            try:
                pct = float(parts[0])
            except ValueError:
                continue
            rank, name = parts[3].strip(), parts[5].strip()
            if pct < 1.0 or not name:
                continue
            if rank == 'G':
                genus_pct[name] = genus_pct.get(name, 0) + pct
            elif rank == 'P':
                phylum_pct[name] = phylum_pct.get(name, 0) + pct
    pool, rank = (genus_pct, 'genus') if genus_pct else (phylum_pct, 'phylum')
    total = sum(pool.values()) or 1
    return [{'name': k, 'abundance': round(v / total * 100, 1), 'rank': rank}
            for k, v in sorted(pool.items(), key=lambda x: -x[1])[:top]]


def run_taxonomy(minio, prefix: str) -> Dict:
    """
    Returns:
        {'organisms': [{'name', 'abundance', 'rank', 'risk_level', 'pathogenicity', 'clinical_relevance'}],
         'abundance_basis': 'assembled_bases' | 'bin_reports' | None,
         'assembled_bp': int | None}
    """
    kraken_keys = _list(minio, f"{prefix}06_kraken2/", recursive=False)
    weighted = _length_weighted(minio, kraken_keys)
    if weighted:
        organisms = [{'name': o['name'], 'abundance': o['abundance'], 'rank': 'genus'} for o in weighted['organisms']]
        basis, assembled = 'assembled_bases', weighted['assembled_bp']
    else:
        organisms = _bin_report_average(minio, kraken_keys)
        basis, assembled = ('bin_reports' if organisms else None), None
    for org in organisms:
        org['risk_level'], org['pathogenicity'], org['clinical_relevance'] = classify(org['name'])
    return {'organisms': organisms, 'abundance_basis': basis, 'assembled_bp': assembled}


# ── Stored copy (map counts, notification emails) ────────────────────────────

async def store_run_results(conn, minio, sample_id: int, pipeline_id: int, prefix: str) -> Dict:
    """
    Replace the run's resistance_genes / detected_organisms rows with the results
    above, so the map and the emails count exactly what the results page shows.

    Returns:
        {'genes': n, 'organisms': n}
    """
    taxonomy = await asyncio.to_thread(run_taxonomy, minio, prefix)
    amr = await asyncio.to_thread(run_amr, minio, prefix)
    async with conn.transaction():
        await conn.execute(
            "DELETE FROM detected_organisms WHERE pipeline_run_id = $1 AND classification_tool IN ('Kraken2', 'Kraken2_reads')",
            pipeline_id
        )
        for org in taxonomy['organisms']:
            await conn.execute(
                """
                INSERT INTO detected_organisms (
                    sample_id, pipeline_run_id, organism_name, scientific_name, taxonomy_rank,
                    classification_tool, abundance, risk_level, pathogenicity
                ) VALUES ($1, $2, $3, $3, $4, 'Kraken2', $5, $6, $7)
                """,
                sample_id, pipeline_id, org['name'][:200], org['rank'], org['abundance'],
                org['risk_level'], org['pathogenicity']
            )
        await conn.execute("DELETE FROM resistance_genes WHERE pipeline_run_id = $1", pipeline_id)
        for g in amr['genes']:
            await conn.execute(
                """
                INSERT INTO resistance_genes (
                    sample_id, pipeline_run_id, gene_name, gene_symbol, accession, detection_tool,
                    coverage, identity, predicted_resistance, resistance_mechanism,
                    confidence_level, quality_score
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $8)
                """,
                sample_id, pipeline_id, g['gene'][:200], g['gene'][:50], g['accession'][:100] or None,
                f"ABRicate/{g['database'] or 'card'}"[:100], g['coverage'], g['identity'],
                [c.strip() for c in g['resistance'].split(';') if c.strip()],
                g['mechanism'][:200], g['risk_level']
            )
    return {'genes': len(amr['genes']), 'organisms': len(taxonomy['organisms'])}
