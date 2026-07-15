#!/usr/bin/env python3
"""
Populate data_lineage by inferring relationships between files in `minio_objects`.
Dry-run by default; use --apply to insert rows.

Heuristic:
 - raw fastq (results/*.fastq.gz) -> 02_filtered
 - 02_filtered -> 03_assembly
 - 03_assembly -> 04_binning
 - 04_binning -> 05_quality
 - 05_quality -> 06_annotation
 - 06_annotation -> 07_abundance

For each target object, match sample code (SRR\d+) in object_key and find latest source object for that sample in the source stage.
"""

import argparse
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

STAGE_ORDER = [
    "raw",
    "02_filtered",
    "03_assembly",
    "04_binning",
    "05_quality",
    "06_kraken2",
    "07_bracken",
]

# match SRR sample codes like SRR11836760
SAMPLE_REGEX = re.compile(r"(SRR\d{5,})")


def run_psql(sql: str):
    cmd = ['docker', 'exec', '-i', 'upgrade_postgres', 'psql', '-U', 'upgrade', '-d', 'upgrade_db', '-v', 'ON_ERROR_STOP=1', '-q', '-t', '-c', sql]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print('PSQL ERROR:', res.stderr)
        raise SystemExit(1)
    return res.stdout.strip()


def find_targets(stage):
    # We store most objects with layer_stage='home' and embed stage folders in object_key
    if stage == 'raw':
        sql = (
            "SELECT object_id, object_key, object_name, process_name, to_char(created_at,'YYYY-MM-DD HH24:MI:SS') "
            "FROM minio_objects WHERE layer_stage = 'home' AND (object_key LIKE '%.fastq.gz' OR object_key LIKE '%.fq.gz') ORDER BY created_at DESC;"
        )
    else:
        # match folder segment like /05_filtered/ or /03_assembly/
        sql = (
            "SELECT object_id, object_key, object_name, process_name, to_char(created_at,'YYYY-MM-DD HH24:MI:SS') "
            f"FROM minio_objects WHERE layer_stage = 'home' AND object_key LIKE '%/{stage}/%' ORDER BY created_at DESC;"
        )
    out = run_psql(sql)
    rows = [r.strip() for r in out.splitlines() if r.strip()]
    targets = []
    for r in rows:
        parts = [p for p in r.split('|')]
        if len(parts) >= 4:
            oid = parts[0].strip()
            key = parts[1].strip()
            name = parts[2].strip()
            process = parts[3].strip()
            created = parts[4].strip() if len(parts) > 4 else None
            targets.append((oid, key, name, process, created))
    return targets


def find_source_for_sample(sample_code, source_stage):
    # Source objects are stored with layer_stage='home' and have stage folder in the path
    if source_stage == 'raw':
        pattern = f"%/{sample_code}.fastq.gz"
        sql = f"SELECT object_id FROM minio_objects WHERE layer_stage = 'home' AND object_key LIKE '{pattern}' ORDER BY created_at DESC LIMIT 1;"
    else:
        sql = (
            f"SELECT object_id FROM minio_objects WHERE layer_stage = 'home' AND object_key LIKE '%/{source_stage}/%{sample_code}%' "
            "ORDER BY created_at DESC LIMIT 1;"
        )
    out = run_psql(sql)
    return out.strip() if out.strip() else None


def lineage_exists(source_oid, target_oid):
    sql = f"SELECT lineage_id FROM data_lineage WHERE source_object_id = {source_oid} AND target_object_id = {target_oid} LIMIT 1;"
    out = run_psql(sql)
    return bool(out.strip())


def insert_lineage(source_oid, target_oid, transformation_type, transformation_process):
    sql = (
        "INSERT INTO data_lineage (source_object_id, target_object_id, transformation_type, transformation_process, transformation_time) "
        + f"VALUES ({source_oid}, {target_oid}, '{transformation_type}', '{transformation_process}', now());"
    )
    run_psql(sql)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()

    total = 0
    created = 0
    missing = 0

    for src, tgt in zip(STAGE_ORDER, STAGE_ORDER[1:]):
        print(f"Processing lineage {src} -> {tgt}")
        targets = find_targets(tgt)
        print(f"  Found {len(targets)} targets in {tgt}")
        for oid, key, name, process, created_at in targets:
            total += 1
            m = SAMPLE_REGEX.search(key)
            if not m:
                missing += 1
                continue
            sample = m.group(1)
            source_oid = find_source_for_sample(sample, src)
            if not source_oid:
                missing += 1
                continue
            # check exists
            if lineage_exists(source_oid, oid):
                continue
            if args.apply:
                insert_lineage(source_oid, oid, f"{src}_to_{tgt}", process)
                created += 1
            else:
                print(f"Would link source {source_oid} -> target {oid} ({sample})")

    print(f"Scanned {total} targets, would create {created if args.apply else 'N'} links, missing sources: {missing}")

if __name__ == '__main__':
    main()
