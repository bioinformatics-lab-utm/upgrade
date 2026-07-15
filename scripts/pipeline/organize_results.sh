#!/bin/bash
# Organize existing results into sample-specific directories

RESULTS_DIR="/home/nicolaedrabcinski/upgrade/results"

# Get list of completed samples from database
samples=$(docker exec upgrade_postgres psql -U upgrade -d upgrade_db -t -c \
    "SELECT DISTINCT sample_name FROM pipeline_runs WHERE status='completed' AND started_at > NOW() - INTERVAL '1 day';" \
    | tr -d ' ')

echo "Organizing results for completed samples..."
echo ""

for sample in $samples; do
    [ -z "$sample" ] && continue
    
    echo "Processing $sample..."
    
    # Create sample result directory if doesn't exist
    mkdir -p "$RESULTS_DIR/$sample"
    
    # Move/symlink results from shared directories to sample-specific
    for stage_dir in 01_QC 02_filtered 03_assembly 04_binning 05_quality 05_filtered 05_drep 05_gtdbtk 06_kraken2 07_bracken 06_annotation 07_amr; do
        if [ -d "$RESULTS_DIR/$stage_dir" ]; then
            # Find files/directories for this sample
            find "$RESULTS_DIR/$stage_dir" -maxdepth 3 -name "*${sample}*" 2>/dev/null | while read item; do
                if [ -e "$item" ]; then
                    rel_path=$(realpath --relative-to="$RESULTS_DIR" "$item")
                    target="$RESULTS_DIR/$sample/$(dirname "$rel_path")"
                    
                    # Create target directory
                    mkdir -p "$target"
                    
                    # Create symlink if doesn't exist
                    link_name="$target/$(basename "$item")"
                    if [ ! -e "$link_name" ]; then
                        ln -s "$(realpath "$item")" "$link_name"
                        echo "  ✓ Linked: $rel_path"
                    fi
                fi
            done
        fi
    done
    
    echo ""
done

echo "Done! Results organized."
