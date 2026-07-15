#!/bin/bash

# Pull all Nextflow containers
# Run with: bash pull_all_containers.sh

set -e

echo "=== Pulling Python base images ==="
docker pull python:3.11
docker pull python:3.9
docker pull python:3.11-slim

echo "=== Pulling StaPH-B images ==="
docker pull staphb/filtlong:0.2.1
docker pull staphb/flye:2.9.2
docker pull staphb/kraken2:2.1.2-no-db
docker pull staphb/bracken:2.9
docker pull staphb/prokka:1.14.6
docker pull staphb/plasmidfinder:2.1.6
docker pull staphb/abricate:1.0.0
docker pull staphb/mummer:3.23
docker pull staphb/fastani:1.33
docker pull staphb/roary:3.13.0
docker pull staphb/panaroo:1.3.2

echo "=== Pulling Biocontainers ==="
docker pull quay.io/biocontainers/nanoplot:1.42.0--pyhdfd78af_0
docker pull quay.io/biocontainers/metabat2:2.18--h6f16272_0
docker pull quay.io/biocontainers/concoct:1.1.0--py27h88e4a8a_0
docker pull quay.io/biocontainers/checkm-genome:1.2.2--pyhdfd78af_1
docker pull quay.io/biocontainers/seqkit:2.12.0--he881be0_1
docker pull quay.io/biocontainers/biopython:1.78
docker pull quay.io/biocontainers/python:3.9
docker pull 'quay.io/biocontainers/mulled-v2-fe8faa35dbf6dc65a0f7f5d4ea12e31a79f73e40:219b6c272b25e7e642ae3ff0bf0c5c81a5135ab4-0'

echo "=== Pulling ONT Research images ==="
docker pull ontresearch/medaka:latest

echo "=== Pulling other tools ==="
docker pull ubuntu:22.04
docker pull jiarong/virsorter:2.2.4
docker pull kbessonov/mob_suite:3.1.9
docker pull ecogenomics/gtdbtk:2.3.2
docker pull davidemms/orthofinder:2.5.5

echo "=== Verifying upgrade-deeparg:latest exists ==="
docker image inspect upgrade-deeparg:latest >/dev/null && echo "✓ upgrade-deeparg:latest" || echo "✗ Need to build upgrade-deeparg:latest"

echo ""
echo "=== Summary ==="
echo "All containers pulled successfully!"
echo "Total images: 30"
