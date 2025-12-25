#!/usr/bin/env python3
"""
Fetch metagenomic sample IDs from NCBI SRA with extended metadata
For Urban Pathogen Genomic Surveillance - Europe focus
"""

import requests
import xml.etree.ElementTree as ET
from datetime import datetime
import json
from typing import List, Dict
import argparse
from collections import Counter

def search_sra(query: str, max_results: int) -> List[str]:
    """Search SRA and return IDs with pagination"""
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    
    # First request to get total count
    params = {'db': 'sra', 'term': query, 'retmax': 0, 'retmode': 'json'}
    r = requests.get(url, params=params)
    r.raise_for_status()
    data = r.json()
    
    total_count = int(data.get('esearchresult', {}).get('count', 0))
    print(f"✓ Found {total_count} total samples")
    
    if max_results and max_results < total_count:
        total_count = max_results
        print(f"  Limiting to {max_results} samples")
    
    # Fetch IDs in batches (NCBI limit is 10000 per request)
    all_ids = []
    batch_size = 10000
    
    for start in range(0, total_count, batch_size):
        batch_max = min(batch_size, total_count - start)
        params = {
            'db': 'sra',
            'term': query,
            'retstart': start,
            'retmax': batch_max,
            'retmode': 'json'
        }
        
        print(f"  Fetching IDs {start+1}-{start+batch_max}...")
        r = requests.get(url, params=params)
        r.raise_for_status()
        data = r.json()
        
        batch_ids = data.get('esearchresult', {}).get('idlist', [])
        all_ids.extend(batch_ids)
    
    print(f"✓ Retrieved {len(all_ids)} IDs")
    return all_ids

def fetch_metadata(ids: List[str]) -> List[Dict]:
    """Fetch extended metadata"""
    if not ids:
        return []
    
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    params = {'db': 'sra', 'id': ','.join(ids), 'retmode': 'xml'}
    
    r = requests.get(url, params=params)
    r.raise_for_status()
    
    root = ET.fromstring(r.content)
    samples = []
    
    for pkg in root.findall('.//EXPERIMENT_PACKAGE'):
        s = parse_sample(pkg)
        if s:
            samples.append(s)
    
    return samples

def parse_sample(pkg: ET.Element) -> Dict:
    """Parse sample with ALL available metadata"""
    try:
        # Accessions
        run = pkg.find('.//RUN')
        exp = pkg.find('.//EXPERIMENT')
        sample = pkg.find('.//SAMPLE')
        study = pkg.find('.//STUDY')
        submission = pkg.find('.//SUBMISSION')
        
        run_id = run.get('accession') if run is not None else 'N/A'
        exp_id = exp.get('accession') if exp is not None else 'N/A'
        sample_id = sample.get('accession') if sample is not None else 'N/A'
        study_id = study.get('accession') if study is not None else 'N/A'
        bioproject = study.get('bioproject_accession') if study is not None else 'N/A'
        
        # File stats
        size_mb = 0
        spots = 0
        bases = 0
        if run is not None:
            f = run.find('.//SRAFile[@supertype="Original"]')
            if f is not None:
                size_mb = round(int(f.get('size', 0)) / 1024 / 1024, 2)
            spots = int(run.get('total_spots', 0))
            bases = int(run.get('total_bases', 0))
        
        # Organism
        organism = 'N/A'
        if sample is not None:
            org = sample.find('.//SCIENTIFIC_NAME')
            organism = org.text if org is not None else 'N/A'
        
        # Sample attributes
        attrs = {}
        if sample is not None:
            for a in sample.findall('.//SAMPLE_ATTRIBUTE'):
                t = a.find('TAG')
                v = a.find('VALUE')
                if t is not None and v is not None:
                    attrs[t.text.lower()] = v.text
        
        # Platform
        plat = pkg.find('.//PLATFORM/*')
        platform = plat.tag if plat is not None else 'N/A'
        inst = plat.find('.//INSTRUMENT_MODEL') if plat is not None else None
        instrument = inst.text if inst is not None else 'N/A'
        
        # Library
        lib = pkg.find('.//LIBRARY_DESCRIPTOR')
        strategy = 'N/A'
        source = 'N/A'
        selection = 'N/A'
        layout = 'N/A'
        if lib is not None:
            strat = lib.find('.//LIBRARY_STRATEGY')
            src = lib.find('.//LIBRARY_SOURCE')
            sel = lib.find('.//LIBRARY_SELECTION')
            lay = lib.find('.//LIBRARY_LAYOUT/*')
            
            strategy = strat.text if strat is not None else 'N/A'
            source = src.text if src is not None else 'N/A'
            selection = sel.text if sel is not None else 'N/A'
            layout = lay.tag if lay is not None else 'N/A'
        
        # Study
        title = 'N/A'
        abstract = 'N/A'
        if study is not None:
            t = study.find('.//STUDY_TITLE')
            a = study.find('.//STUDY_ABSTRACT')
            title = t.text[:100] if t is not None else 'N/A'
            abstract = a.text[:200] if a is not None else 'N/A'
        
        # Publication date
        pub_date = submission.get('published') if submission is not None else 'N/A'
        
        # Calculate read length
        avg_len = round(bases / spots) if spots > 0 else 0
        
        return {
            # === ACCESSIONS ===
            'run_id': run_id,
            'experiment_id': exp_id,
            'sample_id': sample_id,
            'study_id': study_id,
            'bioproject_id': bioproject,
            
            # === SEQUENCING STATS ===
            'file_size_mb': size_mb,
            'total_spots': spots,
            'total_bases': bases,
            'avg_read_length': avg_len,
            
            # === ORGANISM ===
            'organism': organism,
            
            # === PLATFORM ===
            'platform': platform,
            'instrument': instrument,
            
            # === LIBRARY ===
            'strategy': strategy,
            'source': source,
            'selection': selection,
            'layout': layout,
            
            # === STUDY ===
            'study_title': title,
            'study_abstract': abstract,
            'publication_date': pub_date,
            
            # === GEOGRAPHIC ===
            'lat': attrs.get('lat', attrs.get('latitude', 'N/A')),
            'lon': attrs.get('lon', attrs.get('longitude', 'N/A')),
            'geo_loc_name': attrs.get('geo_loc_name', attrs.get('geographic location', 'N/A')),
            'country': attrs.get('country', 'N/A'),
            
            # === SAMPLE METADATA ===
            'collection_date': attrs.get('collection_date', attrs.get('collection date', 'N/A')),
            'isolation_source': attrs.get('isolation_source', attrs.get('isolation source', 'N/A')),
            'env_biome': attrs.get('env_biome', 'N/A'),
            'env_feature': attrs.get('env_feature', 'N/A'),
            'env_material': attrs.get('env_material', 'N/A'),
            'host': attrs.get('host', 'N/A'),
            'sample_type': attrs.get('sample_type', 'N/A'),
            
            # === URLS ===
            'sra_url': f'https://www.ncbi.nlm.nih.gov/sra/{run_id}',
            'biosample_url': f'https://www.ncbi.nlm.nih.gov/biosample/{sample_id}' if sample_id != 'N/A' else 'N/A',
            'bioproject_url': f'https://www.ncbi.nlm.nih.gov/bioproject/{bioproject}' if bioproject != 'N/A' else 'N/A'
        }
    except Exception as e:
        print(f"⚠ Parse error: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description='Fetch metagenomic IDs with extended metadata')
    parser.add_argument('--max-results', type=int, default=None, help='Max results to fetch (default: all)')
    parser.add_argument('--max-size', type=float, help='Max file size MB')
    parser.add_argument('--min-size', type=float, help='Min file size MB')
    parser.add_argument('--min-date', help='Min pub date YYYY/MM/DD')
    parser.add_argument('--sources', nargs='+', default=None)
    parser.add_argument('--layout', choices=['SINGLE', 'PAIRED'])
    parser.add_argument('--has-coords', action='store_true')
    parser.add_argument('--worldwide', action='store_true', help='Search worldwide (not only Europe)')
    parser.add_argument('--geography', default='Europe', help='Geographic region (default: Europe, use --worldwide to disable)')
    parser.add_argument('--output', default='metagenomic_ids.json')
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("NCBI SRA Metagenomic Fetcher - Extended Metadata")
    if args.worldwide:
        print("WORLDWIDE SEARCH")
    else:
        print(f"Region: {args.geography}")
    print("=" * 80)
    
    # Build query
    parts = ['metagenome[Organism]']
    
    # Add geography only if not worldwide
    if not args.worldwide:
        parts.append(f'{args.geography}[All Fields]')
    
    if args.sources:
        parts.append(f'({" OR ".join(args.sources)})')
    if args.min_date:
        today = datetime.now().strftime('%Y/%m/%d')
        parts.append(f'"{args.min_date}"[Publication Date]:"{today}"[Publication Date]')
    
    query = ' AND '.join(parts)
    print(f"\nQuery: {query}\n")
    
    # Search
    ids = search_sra(query, args.max_results)
    if not ids:
        print("✗ No samples found")
        return
    
    # Fetch metadata
    samples = []
    batch_size = 50  # Reduced from 100 to avoid NCBI API errors
    for i in range(0, len(ids), batch_size):
        batch = ids[i:i+batch_size]
        print(f"  Batch {i//batch_size + 1}/{(len(ids) + batch_size - 1)//batch_size}...")
        try:
            samples.extend(fetch_metadata(batch))
        except Exception as e:
            print(f"  ⚠ Batch {i//batch_size + 1} failed: {e}")
            continue
    
    print(f"✓ Fetched {len(samples)} samples\n")
    
    # Filters
    if args.min_size:
        samples = [s for s in samples if s['file_size_mb'] >= args.min_size]
        print(f"✓ Filtered: {len(samples)} samples >= {args.min_size} MB")
    
    if args.max_size:
        samples = [s for s in samples if s['file_size_mb'] <= args.max_size]
        print(f"✓ Filtered: {len(samples)} samples <= {args.max_size} MB")
    
    if args.layout:
        samples = [s for s in samples if s['layout'] == args.layout]
        print(f"✓ Filtered: {len(samples)} samples with {args.layout} layout")
    
    if args.has_coords:
        samples = [s for s in samples if s['lat'] != 'N/A' and s['lon'] != 'N/A']
        print(f"✓ Filtered: {len(samples)} samples with coordinates")
    
    if not samples:
        print("✗ No samples after filtering")
        return
    
    # Sort by size
    samples.sort(key=lambda x: x['file_size_mb'])
    
    # Save
    output = {
        'query': query,
        'timestamp': datetime.now().isoformat(),
        'total_count': len(samples),
        'filters': {
            'geography': 'Worldwide' if args.worldwide else args.geography,
            'sources': args.sources,
            'min_size_mb': args.min_size,
            'max_size_mb': args.max_size,
            'min_date': args.min_date,
            'layout': args.layout,
            'has_coords': args.has_coords,
            'worldwide': args.worldwide
        },
        'samples': samples
    }
    
    with open(args.output, 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"\n✓ Saved {len(samples)} samples to {args.output}")
    
    # Stats
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    
    if samples:
        sizes = [s['file_size_mb'] for s in samples]
        print(f"\nFile sizes: {min(sizes):.1f} - {max(sizes):.1f} MB (avg: {sum(sizes)/len(sizes):.1f} MB, total: {sum(sizes)/1024:.1f} GB)")
        
        print(f"\nTop 10 smallest:")
        print(f"{'Run ID':<15} {'Size':<8} {'Reads':<10} {'Layout':<8} {'Platform':<20} {'Location'}")
        print("-" * 90)
        for s in samples[:10]:
            reads = f"{s['total_spots']/1e6:.1f}M" if s['total_spots'] > 0 else 'N/A'
            loc = s['geo_loc_name'][:20] if s['geo_loc_name'] != 'N/A' else 'N/A'
            print(f"{s['run_id']:<15} {s['file_size_mb']:<8.1f} {reads:<10} {s['layout']:<8} {s['instrument'][:18]:<20} {loc}")
        
        # Distributions
        print(f"\nPlatforms: {dict(Counter(s['platform'] for s in samples).most_common())}")
        print(f"Layouts: {dict(Counter(s['layout'] for s in samples).most_common())}")
        print(f"With coords: {sum(1 for s in samples if s['lat'] != 'N/A')}/{len(samples)}")
    
    print("\n" + "=" * 80)
    print("Download commands (top 5):")
    print("=" * 80)
    for s in samples[:5]:
        print(f"fasterq-dump {s['run_id']} -O data/ -e 8  # {s['file_size_mb']} MB, {s['geo_loc_name']}")

if __name__ == '__main__':
    main()
