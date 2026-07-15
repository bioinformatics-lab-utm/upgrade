#!/bin/bash
# Monitor pipeline progress
# Usage: ./monitor_pipeline.sh <pipeline_id>

PIPELINE_ID=${1:-2}
SAMPLE_CODE=$(docker exec upgrade_postgres psql -U upgrade -d upgrade_db -t -c "SELECT COALESCE(sample_name, 'test_opt_120137') FROM pipeline_runs WHERE pipeline_id = $PIPELINE_ID;")
SAMPLE_CODE=$(echo $SAMPLE_CODE | xargs)  # Trim whitespace

echo "Monitoring Pipeline ID: $PIPELINE_ID"
echo "Sample Code: $SAMPLE_CODE"
echo ""

while true; do
    clear
    echo "========================================"
    echo "Pipeline Progress Monitor"
    echo "========================================"
    echo "Time: $(date '+%Y-%m-%d %H:%M:%S')"
    echo ""
    
    # Database status
    echo "=== Database Status ==="
    docker exec upgrade_postgres psql -U upgrade -d upgrade_db -c \
        "SELECT pipeline_id, status, started_at, completed_at, 
                EXTRACT(EPOCH FROM (COALESCE(completed_at, NOW()) - started_at))/60 as runtime_min
         FROM pipeline_runs WHERE pipeline_id = $PIPELINE_ID;" | head -10
    echo ""
    
    # Nextflow tasks
    if [ -f "/home/nicolaedrabcinski/upgrade/results/$SAMPLE_CODE/nextflow_trace.txt" ]; then
        echo "=== Nextflow Tasks ==="
        TOTAL=$(tail -n +2 "/home/nicolaedrabcinski/upgrade/results/$SAMPLE_CODE/nextflow_trace.txt" | wc -l)
        COMPLETED=$(tail -n +2 "/home/nicolaedrabcinski/upgrade/results/$SAMPLE_CODE/nextflow_trace.txt" | grep "COMPLETED" | wc -l)
        RUNNING=$(tail -n +2 "/home/nicolaedrabcinski/upgrade/results/$SAMPLE_CODE/nextflow_trace.txt" | grep "RUNNING" | wc -l)
        FAILED=$(tail -n +2 "/home/nicolaedrabcinski/upgrade/results/$SAMPLE_CODE/nextflow_trace.txt" | grep "FAILED" | wc -l)
        
        echo "Total: $TOTAL | Completed: $COMPLETED | Running: $RUNNING | Failed: $FAILED"
        echo ""
        
        echo "Last 3 completed tasks:"
        tail -n +2 "/home/nicolaedrabcinski/upgrade/results/$SAMPLE_CODE/nextflow_trace.txt" | \
            grep "COMPLETED" | tail -3 | \
            awk '{printf "  %-30s %10s %10s\n", $4, $10, $12}' | \
            sed 's/^/  /'
        echo ""
    fi
    
    # Directory structure
    echo "=== Output Directories ==="
    find "/home/nicolaedrabcinski/upgrade/results/$SAMPLE_CODE" -maxdepth 1 -type d | \
        tail -n +2 | sort | sed 's|^.*/||' | sed 's/^/  ✓ /'
    echo ""
    
    # File counts in key directories
    if [ -d "/home/nicolaedrabcinski/upgrade/results/$SAMPLE_CODE/04_metabat2" ]; then
        METABAT2_BINS=$(ls "/home/nicolaedrabcinski/upgrade/results/$SAMPLE_CODE/04_metabat2"/*.fa 2>/dev/null | wc -l)
        echo "  MetaBAT2 bins: $METABAT2_BINS"
    fi
    
    if [ -d "/home/nicolaedrabcinski/upgrade/results/$SAMPLE_CODE/04_concoct" ]; then
        CONCOCT_BINS=$(ls "/home/nicolaedrabcinski/upgrade/results/$SAMPLE_CODE/04_concoct"/*.fa 2>/dev/null | wc -l)
        echo "  CONCOCT bins: $CONCOCT_BINS"
    fi
    
    if [ -f "/home/nicolaedrabcinski/upgrade/results/$SAMPLE_CODE/05_checkm/test_opt_120137_metabat2_checkm_summary.tsv" ]; then
        HIGH_Q=$(awk 'NR>1 && $12>90 && $13<5 {count++} END {print count+0}' "/home/nicolaedrabcinski/upgrade/results/$SAMPLE_CODE/05_checkm/test_opt_120137_metabat2_checkm_summary.tsv" 2>/dev/null)
        MED_Q=$(awk 'NR>1 && $12>50 && $13<10 {count++} END {print count+0}' "/home/nicolaedrabcinski/upgrade/results/$SAMPLE_CODE/05_checkm/test_opt_120137_metabat2_checkm_summary.tsv" 2>/dev/null)
        echo "  Quality: High=$HIGH_Q, Medium=$MED_Q"
    fi
    
    if [ -d "/home/nicolaedrabcinski/upgrade/results/$SAMPLE_CODE/05_drep/dereplicated_genomes" ]; then
        DEREP_BINS=$(ls "/home/nicolaedrabcinski/upgrade/results/$SAMPLE_CODE/05_drep/dereplicated_genomes"/*.fa 2>/dev/null | wc -l)
        echo "  Dereplicated bins: $DEREP_BINS"
    fi
    
    echo ""
    echo "Press Ctrl+C to exit. Refreshing in 30 seconds..."
    sleep 30
done
