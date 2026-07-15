#!/usr/bin/env python3
"""
Quick scan - first 10000 metagenomic samples
"""

import requests
import xml.etree.ElementTree as ET
import json
import time

def search_metagenomes(max_results=10000):
    """Get first N metagenomic sample IDs"""
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    query = 'metagenome[Organism]'
    
    params = {
        'db': 'sra',
        'term': query,
        'retmax': max_results,
        'retmode': 'json'
    }
    
    print(f"Searching for first {max_results} metagenomic samples...")
    r = requests.get(url, params=params)
    r.raise_for_status()
    data = r.json()
    
    ids = data.get('esearchresult', {}).get('idlist', [])
    total = int(data.get('esearchresult', {}).get('count', 0))
    
    print(f"✓ Got {len(ids)} IDs (total available: {total:,})")
    return ids

def fetch_coords(ids):
    """Fetch coordinates for batch"""
    if not ids:
        return []
    
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    params = {'db': 'sra', 'id': ','.join(ids), 'retmode': 'xml'}
    
    try:
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
    except:
        return []
    
    root = ET.fromstring(r.content)
    results = []
    
    for pkg in root.findall('.//EXPERIMENT_PACKAGE'):
        try:
            run = pkg.find('.//RUN')
            if not run:
                continue
            
            run_id = run.get('accession')
            sample = pkg.find('.//SAMPLE')
            if not sample:
                continue
            
            lat = lon = geo_loc = None
            
            for attr in sample.findall('.//SAMPLE_ATTRIBUTE'):
                tag = attr.find('TAG')
                val = attr.find('VALUE')
                if not tag or not val:
                    continue
                
                t = tag.text.lower()
                v = val.text
                
                if t in ['lat', 'latitude']:
                    try:
                        lat = float(v)
                    except:
                        pass
                elif t in ['lon', 'longitude']:
                    try:
                        lon = float(v)
                    except:
                        pass
                elif t in ['geo_loc_name', 'geographic location']:
                    geo_loc = v
            
            if lat is not None and lon is not None:
                f = run.find('.//SRAFile[@supertype="Original"]')
                size_mb = round(int(f.get('size', 0)) / 1024 / 1024, 2) if f else 0
                
                results.append({
                    'run_id': run_id,
                    'lat': lat,
                    'lon': lon,
                    'geo_loc_name': geo_loc or 'Unknown',
                    'file_size_mb': size_mb
                })
        except:
            continue
    
    return results

print("="*80)
print("Quick Scan - First 10,000 Metagenomic Samples")
print("="*80)

ids = search_metagenomes(10000)

print(f"\nScanning {len(ids)} samples for coordinates...")
all_coords = []
batch_size = 20

for i in range(0, len(ids), batch_size):
    batch = ids[i:i+batch_size]
    print(f"  [{i//batch_size + 1}/{len(ids)//batch_size}] Batch {i}-{i+batch_size}...", end='')
    
    coords = fetch_coords(batch)
    if coords:
        all_coords.extend(coords)
        print(f" {len(coords)} with coords (total: {len(all_coords)})")
    else:
        print(" none")
    
    time.sleep(0.5)

all_coords.sort(key=lambda x: x['file_size_mb'])

output = {
    'scanned': len(ids),
    'with_coords': len(all_coords),
    'percentage': round(len(all_coords)/len(ids)*100, 2),
    'samples': all_coords
}

with open('/tmp/quick_scan_coords.json', 'w') as f:
    json.dump(output, f, indent=2)

with open('/tmp/coord_sample_ids.txt', 'w') as f:
    for s in all_coords:
        f.write(f"{s['run_id']}\n")

print("\n" + "="*80)
print(f"DONE: {len(all_coords)} samples with coordinates ({output['percentage']}%)")
print(f"Saved to: /tmp/quick_scan_coords.json")
print(f"IDs saved to: /tmp/coord_sample_ids.txt")

if all_coords:
    print(f"\nSmallest 10:")
    for s in all_coords[:10]:
        print(f"  {s['run_id']}: {s['file_size_mb']}MB - {s['geo_loc_name'][:50]}")
