#!/usr/bin/env python3
"""
Secure pipeline submission via authenticated API
Uses confirm-upload endpoint for existing data
"""
import requests
import json
import sys

API_BASE = "http://localhost:8000/api"

# Step 1: Login
print("=" * 60)
print("SECURE PIPELINE SUBMISSION")
print("=" * 60)
print("\nStep 1: Authentication...")

login_payload = {
    "username": "nicolaedrabcinski",
    "password": "Drabcinski!1"
}

try:
    login_response = requests.post(
        f"{API_BASE}/auth/login",
        json=login_payload
    )
    
    if login_response.status_code != 200:
        print(f"✗ Login failed: {login_response.status_code}")
        print(login_response.text)
        sys.exit(1)
    
    login_data = login_response.json()
    token = login_data.get('token')
    user = login_data.get('user', {})
    
    print(f"✓ Authenticated as: {user.get('username')} ({user.get('email')})")
    print(f"✓ Token acquired")
    
except Exception as e:
    print(f"✗ Authentication error: {e}")
    sys.exit(1)

# Step 2: Submit via confirm-upload (for existing data in /data/zymo_mock)
print("\nStep 2: Submitting pipeline via confirm-upload...")

payload = {
    "sample_code": "ZYMO_API_002",  # New sample code
    "sample_type": "nanopore",
    "collection_date": "2026-01-13",
    "pipeline_name": "nextflow_pipeline",
    "notes": "Secure API submission with 12h timeout - fixed RQ config",
    "parameters": {
        "flye_genome_size": "50m",
        "flye_meta": True,
        "threads": 32
    },
    "skip_bronze": True,  # Data already in /data/zymo_mock
    "input_dir": "/data/zymo_mock",
    "output_dir": "/results/zymo_api_002"
}

headers = {"Authorization": f"Bearer {token}"}

try:
    response = requests.post(
        f"{API_BASE}/pipeline/confirm-upload",
        json=payload,
        headers=headers
    )
    
    print(f"\nStatus: {response.status_code}")
    
    if response.status_code in [200, 201]:
        result = response.json()
        print("\n" + "=" * 60)
        print("✓ PIPELINE LAUNCHED SUCCESSFULLY")
        print("=" * 60)
        print(f"Pipeline ID:  {result.get('pipeline_id')}")
        print(f"Sample Code:  {result.get('sample_code')}")
        print(f"Status:       {result.get('status')}")
        print(f"Job Timeout:  12 hours (43200s)")
        print(f"Using -resume: Skips cached FILTLONG, NANOPLOT, FLYE")
        print("=" * 60)
    else:
        print(f"\n✗ Submission failed")
        print(response.text)
        sys.exit(1)
        
except Exception as e:
    print(f"✗ Error: {e}")
    sys.exit(1)
