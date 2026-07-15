#!/usr/bin/env python3
"""
Geocode sample locations from city names or geo_loc_name to coordinates
Uses Nominatim (OpenStreetMap) for free geocoding
"""

import json
import time
import requests
from typing import Optional, Tuple
import argparse

def geocode_location(location: str) -> Optional[Tuple[float, float]]:
    """Geocode a location string to lat/lon coordinates"""
    if not location or location in ['N/A', '', None]:
        return None
    
    # Clean location string
    location = location.strip()
    
    # Try Nominatim (OpenStreetMap) - free, no API key needed
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        'q': location,
        'format': 'json',
        'limit': 1
    }
    headers = {
        'User-Agent': 'MetagenomicPipeline/1.0'
    }
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=5)
        response.raise_for_status()
        data = response.json()
        
        if data and len(data) > 0:
            lat = float(data[0]['lat'])
            lon = float(data[0]['lon'])
            return (lat, lon)
    except Exception as e:
        print(f"  ⚠ Geocoding failed for '{location}': {e}")
    
    return None

def extract_location_from_metadata(sample: dict) -> Optional[str]:
    """Extract location from various metadata fields"""
    import re
    
    # Priority order for location extraction
    fields = [
        'geo_loc_name',
        'country',
        'study_abstract',  # Check abstract first (more detailed)
        'study_title',
        'isolation_source'
    ]
    
    for field in fields:
        value = sample.get(field, 'N/A')
        if value and value != 'N/A':
            # For study_title/abstract, try to extract city names
            if field in ['study_title', 'study_abstract']:
                # Match patterns like "Beijing", "Xi'an", "New York", etc.
                # Look for capitalized words, possibly with apostrophes or hyphens
                patterns = [
                    r"([A-Z][a-z]+(?:[''-][A-Z]?[a-z]+)?(?:\s+[A-Z][a-z]+)?)\s+(?:city|cities|public places|region|area)",  # "Xi'an public places"
                    r"(?:in|from|at|near)\s+([A-Z][a-z]+(?:[''-][A-Z]?[a-z]+)?(?:\s+[A-Z][a-z]+)?)",  # "in Beijing", "from Xi'an"
                    r"([A-Z][a-z]+(?:[''-][A-Z]?[a-z]+)?(?:\s+[A-Z][a-z]+)?),\s*(?:China|USA|UK|India|Japan|Korea|Germany|France)",  # "Beijing, China"
                ]
                for pattern in patterns:
                    match = re.search(pattern, value)
                    if match:
                        city = match.group(1).strip()
                        # Filter out common false positives
                        if city.lower() not in ['april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december', 'january', 'february', 'march']:
                            return city
            else:
                return value
    
    return None

def main():
    parser = argparse.ArgumentParser(description='Geocode samples with location names')
    parser.add_argument('input', help='Input JSON file with samples')
    parser.add_argument('output', help='Output JSON file with coordinates')
    parser.add_argument('--delay', type=float, default=1.0, help='Delay between geocoding requests (seconds)')
    parser.add_argument('--limit', type=int, help='Limit number of samples to geocode')
    
    args = parser.parse_args()
    
    print("="*80)
    print("Sample Geocoder")
    print("="*80)
    
    # Load samples
    with open(args.input) as f:
        data = json.load(f)
    
    if isinstance(data, dict) and 'samples' in data:
        samples = data['samples']
    elif isinstance(data, list):
        samples = data
    else:
        samples = [data]
    
    print(f"✓ Loaded {len(samples)} samples")
    
    if args.limit:
        samples = samples[:args.limit]
        print(f"  Limiting to {args.limit} samples")
    
    # Geocode samples
    geocoded = []
    skipped = 0
    failed = 0
    
    for i, sample in enumerate(samples, 1):
        # Skip if already has coordinates
        if sample.get('lat') not in ['N/A', '', None] and sample.get('lon') not in ['N/A', '', None]:
            try:
                float(sample['lat'])
                float(sample['lon'])
                geocoded.append(sample)
                print(f"[{i}/{len(samples)}] ✓ {sample['run_id']} - Already has coords: {sample['lat']}, {sample['lon']}")
                continue
            except:
                pass
        
        # Extract location
        location = extract_location_from_metadata(sample)
        
        if not location:
            skipped += 1
            print(f"[{i}/{len(samples)}] ⊘ {sample['run_id']} - No location found")
            continue
        
        print(f"[{i}/{len(samples)}] → {sample['run_id']} - Geocoding '{location}'...", end='')
        
        # Geocode
        coords = geocode_location(location)
        
        if coords:
            sample['lat'] = coords[0]
            sample['lon'] = coords[1]
            sample['geocoded_from'] = location
            geocoded.append(sample)
            print(f" ✓ {coords[0]:.4f}, {coords[1]:.4f}")
        else:
            failed += 1
            print(f" ✗ Failed")
        
        # Rate limiting
        time.sleep(args.delay)
    
    print("\n" + "="*80)
    print(f"Geocoding Complete")
    print("="*80)
    print(f"Total samples: {len(samples)}")
    print(f"Successfully geocoded: {len(geocoded)}")
    print(f"Already had coords: {len([s for s in geocoded if 'geocoded_from' not in s])}")
    print(f"Newly geocoded: {len([s for s in geocoded if 'geocoded_from' in s])}")
    print(f"No location data: {skipped}")
    print(f"Geocoding failed: {failed}")
    
    # Save results
    if geocoded:
        with open(args.output, 'w') as f:
            json.dump({'samples': geocoded}, f, indent=2)
        print(f"\n✓ Saved {len(geocoded)} samples with coordinates to {args.output}")
    else:
        print("\n✗ No samples with coordinates to save")

if __name__ == '__main__':
    main()
