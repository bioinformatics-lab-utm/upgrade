#!/usr/bin/env python3
"""
Full scan of NCBI SRA for metagenomic samples with coordinates
Saves progress and handles API limits
"""

import requests
import xml.etree.ElementTree as ET
import json
import time
from pathlib import Path

def search_all_metagenomic_ids():
    """Get ALL metagenomic sample IDs"""
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    query = 'metagenome[Organism]'
    
    # Get total count
    params = {'db': 'sra', 'term': query, 'retmax': 0, 'retmode': 'json'}
    r = requests.get(url, params=params)
    r.raise_for_status()
    data = r.json()
    
    total_count = int(data.get('esearchresult', {}).get('count', 0))
    print(f"✓ Total metagenomic samples in SRA: {total_count:,}")
    
    # NCBI allows max 10000 per query, so we need multiple queries
    all_ids = []
    batch_size = 10000
    
    for start in range(0, total_count, batch_size):
        params = {
            'db': 'sra',
            'term': query,
            'retstart': start,
            'retmax': batch_size,
            'retmode': 'json'
        }
        
        print(f"  Fetching ID batch {start//batch_size + 1} ({start:,} - {min(start+batch_size, total_count):,})...")
        r = requests.get(url, params=params)
        r.raise_for_status()
        data = r.json()
        
        batch_ids = data.get('esearchresult', {}).get('idlist', [])
        all_ids.extend(batch_ids)
        time.sleep(0.5)  # Be nice to NCBI
    
    print(f"✓ Retrieved {len(all_ids):,} IDs")
    return all_ids

def fetch_coordinates_only(ids):
    """Fetch only coordinate data for a batch of IDs"""
    if not ids:
        return []
    
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    params = {'db': 'sra', 'id': ','.join(ids), 'retmode': 'xml'}
    
    try:
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
    except Exception as e:
        print(f"    ⚠ Fetch error: {e}")
        return []
    
    root = ET.fromstring(r.content)
    results = []
    
    for pkg in root.findall('.//EXPERIMENT_PACKAGE'):
        try:
            # Get run accession
            run = pkg.find('.//RUN')
            if run is None:
                continue
            run_id = run.get('accession')
            
            # Get coordinates from sample attributes
            sample = pkg.find('.//SAMPLE')
            if sample is None:
                continue
            
            lat = None
            lon = None
            geo_loc = None
            
            for attr in sample.findall('.//SAMPLE_ATTRIBUTE'):
                tag = attr.find('TAG')
                val = attr.find('VALUE')
                if tag is None or val is None:
                    continue
                
                tag_text = tag.text.lower()
                val_text = val.text
                
                if tag_text in ['lat', 'latitude']:
                    try:
                        lat = float(val_text)
                    except:
                        pass
                elif tag_text in ['lon', 'longitude']:
                    try:
                        lon = float(val_text)
                    except:
                        pass
                elif tag_text in ['geo_loc_name', 'geographic location']:
                    geo_loc = val_text
            
            # Only include if has valid numeric coordinates
            if lat is not None and lon is not None:
                # Get file size
                size_mb = 0
                f = run.find('.//SRAFile[@supertype="Original"]')
                if f is not None:
                    size_mb = round(int(f.get('size', 0)) / 1024 / 1024, 2)
                
                results.append({
                    'run_id': run_id,
                    'lat': lat,
                    'lon': lon,
                    'geo_loc_name': geo_loc or 'Unknown',
                    'file_size_mb': size_mb
                })
        except Exception as e:
            continue
    
    return results

def main():
    output_file = Path('/tmp/all_metagenomes_with_coords.json')
    progress_file = Path('/tmp/scan_progress.json')
    
    print("="*80)
    print("NCBI SRA Full Scan - Metagenomic Samples with Coordinates")
    print("="*80)
    
    # Load progress if exists
    start_idx = 0
    all_samples = []
    
    if progress_file.exists():
        with open(progress_file, 'r') as f:
            progress = json.load(f)
            start_idx = progress.get('last_processed_idx', 0)
            all_samples = progress.get('samples_with_coords', [])
        print(f"✓ Resuming from index {start_idx:,}, found {len(all_samples)} samples so far")
    
    # Get all IDs
    print("\n[1/2] Getting all metagenomic sample IDs...")
    all_ids = search_all_metagenomic_ids()
    
    # Process in small batches
    print(f"\n[2/2] Scanning {len(all_ids):,} samples for coordinates...")
    print(f"      Starting from index {start_idx:,}")
    
    batch_size = 20  # Small batch to avoid API errors
    total_batches = (len(all_ids) + batch_size - 1) // batch_size
    
    for i in range(start_idx, len(all_ids), batch_size):
        batch_num = i // batch_size + 1
        batch = all_ids[i:i+batch_size]
        
        print(f"  [{batch_num:,}/{total_batches:,}] Processing IDs {i:,}-{min(i+batch_size, len(all_ids)):,}...", end='')
        
        coords = fetch_coordinates_only(batch)
        if coords:
            all_samples.extend(coords)
            print(f" Found {len(coords)} with coords! (Total: {len(all_samples):,})")
        else:
            print(" No coords")
        
        # Save progress every 50 batches
        if batch_num % 50 == 0:
            with open(progress_file, 'w') as f:
                json.dump({
                    'last_processed_idx': i + batch_size,
                    'samples_with_coords': all_samples,
                    'total_scanned': i + batch_size,
                    'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
                }, f, indent=2)
            print(f"    💾 Progress saved: {len(all_samples):,} samples with coords")
        
        time.sleep(0.4)  # Rate limiting
    
    # Sort by file size
    all_samples.sort(key=lambda x: x['file_size_mb'])
    
    # Save final results
    output = {
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'total_scanned': len(all_ids),
        'total_with_coords': len(all_samples),
        'percentage': round(len(all_samples) / len(all_ids) * 100, 2),
        'samples': all_samples
    }
    
    with open(output_file, 'w') as f:
        json.dump(output, f, indent=2)
    
    print("\n" + "="*80)
    print("SCAN COMPLETE")
    print("="*80)
    print(f"Total samples scanned: {len(all_ids):,}")
    print(f"Samples with coordinates: {len(all_samples):,} ({output['percentage']}%)")
    print(f"\nSaved to: {output_file}")
    
    if all_samples:
        sizes = [s['file_size_mb'] for s in all_samples]
        print(f"\nFile size range: {min(sizes):.1f} - {max(sizes):.1f} MB")
        print(f"Average size: {sum(sizes)/len(sizes):.1f} MB")
        
        print(f"\nSmallest 10 samples:")
        for s in all_samples[:10]:
            print(f"  {s['run_id']}: {s['file_size_mb']:.1f}MB - {s['geo_loc_name'][:40]}")
    
    # Save just the IDs
    ids_file = Path('/tmp/metagenome_ids_with_coords.txt')
    with open(ids_file, 'w') as f:
        for s in all_samples:
            f.write(f"{s['run_id']}\n")
    print(f"\nSample IDs saved to: {ids_file}")

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠ Interrupted by user. Progress saved, you can resume later.")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
