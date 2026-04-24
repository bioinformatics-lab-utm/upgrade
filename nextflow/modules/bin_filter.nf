process BIN_FILTER {
    tag "$sample_id"
    label 'process_low'

    container 'python:3.9'  // Use full image (not slim) - includes procps package for Nextflow metrics

    publishDir "${params.outdir}/05_filtered/${binner_name}", mode: 'copy', pattern: "*_filtered_bins"
    publishDir "${params.outdir}/05_filtered/${binner_name}", mode: 'copy', pattern: "*_filter_report.txt"

    input:
    tuple val(sample_id), path(bins), path(checkm_summary)
    val binner_name

    output:
    tuple val(sample_id), path("${sample_id}_${binner_name}_filtered_bins/*"), emit: filtered_bins, optional: true
    tuple val(sample_id), path("${sample_id}_${binner_name}_filter_report.txt"), emit: report
    path "versions.yml", emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    def completeness_threshold = params.bin_filter_completeness ?: 50
    def contamination_threshold = params.bin_filter_contamination ?: 10
    def skip_filter = params.skip_bin_quality_filter ?: false
    
    """
    # Ensure all files are accessible (work directory permissions fix)
    umask 0000
    
    python3 << 'EOF'
import os
import shutil
import sys
from pathlib import Path

skip_quality_filter = "${skip_filter}" == "true"

print(f"Starting bin filtering for ${sample_id} (${binner_name})")
if skip_quality_filter:
    print(f"Quality filtering DISABLED - all bins will be passed through")
else:
    print(f"Quality thresholds: Completeness >${completeness_threshold}%, Contamination <${contamination_threshold}%")

# Create output directory
output_dir = Path("${sample_id}_${binner_name}_filtered_bins")
output_dir.mkdir(exist_ok=True)
os.chmod(output_dir, 0o777)  # Allow Nextflow to read outputs from any Docker user

# Read CheckM summary file (will be copied by stageInMode='copy')
checkm_file = "${checkm_summary}"
high_quality_bins = []
medium_quality_bins = []
low_quality_bins = []

try:
    with open(checkm_file, 'r') as f:
        lines = f.readlines()
        
        if len(lines) < 2:
            print("WARNING: CheckM summary file is empty or has no data")
            with open("${sample_id}_${binner_name}_filter_report.txt", 'w') as report:
                report.write(f"Bin Filtering Report for ${sample_id} (${binner_name})\\n")
                report.write("=" * 80 + "\\n")
                report.write("No bins analyzed by CheckM\\n")
            sys.exit(0)
        
        # Parse header to find column indices
        header = lines[0].strip().split('\\t')
        try:
            bin_col = header.index('Bin Id')
            completeness_col = header.index('Completeness')
            contamination_col = header.index('Contamination')
        except ValueError as e:
            print(f"ERROR: Could not find required columns in CheckM summary: {e}")
            with open("${sample_id}_${binner_name}_filter_report.txt", 'w') as report:
                report.write(f"Bin Filtering Report for ${sample_id} (${binner_name})\\n")
                report.write("=" * 80 + "\\n")
                report.write(f"ERROR: Invalid CheckM summary format: {e}\\n")
            sys.exit(0)
        
        # Process bins
        for line in lines[1:]:
            fields = line.strip().split('\\t')
            if len(fields) < max(bin_col, completeness_col, contamination_col) + 1:
                continue
                
            bin_id = fields[bin_col]
            try:
                completeness = float(fields[completeness_col])
                contamination = float(fields[contamination_col])
            except (ValueError, IndexError):
                print(f"WARNING: Could not parse metrics for bin {bin_id}")
                continue
            
            # Quality categorization
            if skip_quality_filter:
                # No filtering - pass all bins
                quality = "PASSED"
                medium_quality_bins.append((bin_id, completeness, contamination))
            elif completeness > 90 and contamination < 5:
                quality = "HIGH"
                high_quality_bins.append((bin_id, completeness, contamination))
            elif completeness > ${completeness_threshold} and contamination < ${contamination_threshold}:
                quality = "MEDIUM"
                medium_quality_bins.append((bin_id, completeness, contamination))
            else:
                quality = "LOW"
                low_quality_bins.append((bin_id, completeness, contamination))
            
            # Copy high and medium quality bins to output (or all if skip_filter)
            if skip_quality_filter or quality in ["HIGH", "MEDIUM"]:
                bin_file = None
                for ext in [".fa", ".fasta", ".fa.gz", ".fasta.gz"]:
                    candidate = Path(bin_id + ext)
                    if candidate.exists():
                        bin_file = candidate
                        break

                if bin_file is not None:
                    dest = output_dir / bin_file.name
                    shutil.copy2(bin_file, dest)
                    print(f"✓ [{quality}] {bin_id}: {completeness:.1f}% complete, {contamination:.1f}% contamination")
                else:
                    print(f"WARNING: Bin file not found: {bin_id} (tried .fa, .fasta, .fa.gz, .fasta.gz)")

except Exception as e:
    print(f"ERROR processing CheckM file: {e}")
    with open("${sample_id}_${binner_name}_filter_report.txt", 'w') as report:
        report.write(f"Bin Filtering Report for ${sample_id} (${binner_name})\\n")
        report.write("=" * 80 + "\\n")
        report.write(f"ERROR: {e}\\n")
    sys.exit(0)

# Generate report
total_bins = len(high_quality_bins) + len(medium_quality_bins) + len(low_quality_bins)
filtered_bins = len(high_quality_bins) + len(medium_quality_bins)

report_file = "${sample_id}_${binner_name}_filter_report.txt"
with open(report_file, 'w') as report:
    report.write(f"Bin Filtering Report for ${sample_id} (${binner_name})\\n")
    report.write("=" * 80 + "\\n\\n")
    
    if skip_quality_filter:
        report.write(f"Quality Filtering: DISABLED (all bins passed through)\\n\\n")
    else:
        report.write(f"Quality Thresholds:\\n")
        report.write(f"  Completeness: >${completeness_threshold}%\\n")
        report.write(f"  Contamination: <${contamination_threshold}%\\n\\n")
    
    report.write(f"Summary:\\n")
    report.write(f"  Total bins analyzed: {total_bins}\\n")
    report.write(f"  High quality bins (>90% complete, <5% contamination): {len(high_quality_bins)}\\n")
    report.write(f"  Medium quality bins (>${completeness_threshold}% complete, <${contamination_threshold}% contamination): {len(medium_quality_bins)}\\n")
    report.write(f"  Low quality bins (filtered out): {len(low_quality_bins)}\\n")
    report.write(f"  Bins passed to annotation: {filtered_bins}\\n")
    
    if total_bins > 0:
        report.write(f"  Pass rate: {filtered_bins/total_bins*100:.1f}%\\n\\n")
    else:
        report.write(f"  Pass rate: N/A\\n\\n")
    
    if high_quality_bins:
        report.write(f"\\nHigh Quality Bins ({len(high_quality_bins)}):\\n")
        report.write("-" * 80 + "\\n")
        for bin_id, comp, cont in sorted(high_quality_bins, key=lambda x: x[1], reverse=True):
            report.write(f"  {bin_id:<40} {comp:>6.1f}% complete  {cont:>5.1f}% contamination\\n")
    
    if medium_quality_bins:
        report.write(f"\\nMedium Quality Bins ({len(medium_quality_bins)}):\\n")
        report.write("-" * 80 + "\\n")
        for bin_id, comp, cont in sorted(medium_quality_bins, key=lambda x: x[1], reverse=True):
            report.write(f"  {bin_id:<40} {comp:>6.1f}% complete  {cont:>5.1f}% contamination\\n")
    
    if low_quality_bins:
        report.write(f"\\nLow Quality Bins - FILTERED OUT ({len(low_quality_bins)}):\\n")
        report.write("-" * 80 + "\\n")
        for bin_id, comp, cont in sorted(low_quality_bins, key=lambda x: x[1], reverse=True):
            report.write(f"  {bin_id:<40} {comp:>6.1f}% complete  {cont:>5.1f}% contamination\\n")

# Fix permissions for Nextflow to read outputs
os.chmod(report_file, 0o666)

# Create placeholder if no bins passed filter
if filtered_bins == 0:
    print("WARNING: No bins passed quality filter")
    placeholder = output_dir / ".no_bins_passed_filter"
    placeholder.touch()

print(f"\\nFiltering complete: {filtered_bins}/{total_bins} bins passed quality filter")
EOF

    # Fix permissions on output directory and all files
    chmod -R 777 ${sample_id}_${binner_name}_filtered_bins/ 2>/dev/null || true

    cat > versions.yml << END_VERSIONS
"${task.process}":
    python: \$(python3 --version 2>&1 | sed 's/Python //')
END_VERSIONS
    """
}
