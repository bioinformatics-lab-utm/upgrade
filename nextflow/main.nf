#!/usr/bin/env nextflow

nextflow.enable.dsl = 2

// Print help message
if (params.help) {
    log.info """
    UPGRADE - Environmental Genomic Surveillance Pipeline
    ================================================
    
    Usage:
    nextflow run main.nf [options]
    
    Input options:
    --input_dir    Path to directory containing ONT FASTQ files (default: test_data/ont_data)
    --outdir       Output directory (default: results)
    
    QC options:
    --nanoplot_format                Format for NanoPlot outputs (default: png)
    
    Filtering options:
    --filtlong_min_length           Minimum read length in bp (default: 1000)
    --filtlong_keep_percent         Percentage of best reads to keep (default: 90)
    --filtlong_min_quality          Minimum mean quality score (default: 10)
    
    Assembly options:
    --flye_mode                     Sequencing technology (default: --nano-raw)
                                    Options: --nano-raw, --nano-hq, --nano-corr,
                                            --pacbio-raw, --pacbio-hifi, --pacbio-corr
    --flye_genome_size              Estimated genome size (default: 5m)
                                    Examples: 5m (5 megabases), 2.6g (2.6 gigabases)
    --flye_iterations               Number of polishing iterations (default: 1)
    --flye_meta                     Enable metagenome mode (default: false)
        Contig filtering options:
    --contig_min_length             Minimum contig length to keep after assembly (default: 1000)
        Binning options:
    --metabat2_min_contig           Minimum contig length for MetaBAT2 (default: 2500)
    --metabat2_min_bin              Minimum bin size for MetaBAT2 (default: 200000)
    --concoct_min_contig            Minimum contig length for CONCOCT (default: 1000)
    --concoct_chunk_size            Chunk size for CONCOCT (default: 10000)
    --concoct_overlap_size          Overlap size for CONCOCT (default: 0)
    
    Quality assessment options:
    --checkm_extension              File extension for CheckM (default: fa)
    --skip_bin_quality_filter       Skip quality-based bin filtering, pass all bins (default: false)
    --bin_filter_completeness       Minimum completeness for bin filtering (default: 50%)
    --bin_filter_contamination      Maximum contamination for bin filtering (default: 10%)
    
    Dereplication options:
    --drep_ani                      ANI threshold for species clusters (default: 0.95)
    --drep_completeness             Minimum completeness for dRep (default: 50%)
    --drep_contamination            Maximum contamination for dRep (default: 10%)
    --drep_completeness_weight      Weight for completeness in scoring (default: 1)
    --drep_contamination_weight     Weight for contamination penalty (default: 5)
    
    GTDB-Tk taxonomy options:
    --gtdbtk_db                     Path to GTDB-Tk database (default: null, skips GTDB-Tk)
    --gtdbtk_min_perc_aa            Minimum percent alignment for classification (default: 10%)
    --gtdbtk_pplacer_cpus           CPUs for pplacer step (default: auto = threads/2)
    
    Taxonomic classification options:
    --kraken2_db                    Path to Kraken2 database (default: kraken2_db)
    
    Resource options:
    --threads      Number of threads (default: 30)
    --memory       Memory allocation (default: 8 GB)
    
    Other options:
    --help         Print this help message
    
    Examples:
    nextflow run main.nf -profile docker --input_dir data/ont_reads --filtlong_min_length 1500
    nextflow run main.nf -profile docker --flye_mode '--nano-hq' --flye_genome_size '10m'
    nextflow run main.nf -profile docker --flye_meta true  # For metagenome assembly
    nextflow run main.nf -profile docker --metabat2_min_contig 3000 --concoct_min_contig 1500
    """
    exit 0
}

// Print pipeline info
log.info """
    UPGRADE PIPELINE - Environmental Genomic Surveillance
    =====================================================
    input_dir              : ${params.input_dir}
    outdir                 : ${params.outdir}
    threads                : ${params.threads}
    
    Filtlong parameters:
    min_length             : ${params.filtlong_min_length} bp
    keep_percent           : ${params.filtlong_keep_percent}%
    min_quality            : ${params.filtlong_min_quality}
    
    Flye parameters:
    mode                   : ${params.flye_mode}
    genome_size            : ${params.flye_genome_size}
    iterations             : ${params.flye_iterations}
    meta_mode              : ${params.flye_meta}
    
    Contig filtering:
    min_length             : ${params.contig_min_length ?: 1000} bp
    
    Binning parameters:
    MetaBAT2 min contig    : ${params.metabat2_min_contig ?: 2500} bp
    MetaBAT2 min bin       : ${params.metabat2_min_bin ?: 200000} bp
    CONCOCT min contig     : ${params.concoct_min_contig ?: 1000} bp
    CONCOCT chunk size     : ${params.concoct_chunk_size ?: 10000} bp
    
    CheckM extension       : ${params.checkm_extension ?: 'fa'}
    
    Kraken2 database       : ${params.kraken2_db ?: 'kraken2_db'}
"""

// Import modules
include { NANOPLOT } from './modules/nanoplot.nf'
include { FILTLONG } from './modules/filtlong.nf'
include { FLYE } from './modules/flye.nf'
include { FILTER_CONTIGS } from './modules/filter_contigs.nf'
include { GUNZIP } from './modules/gunzip.nf'
include { MINIMAP2_MAPPING } from './modules/minimap2_mapping.nf'
include { ASSEMBLY_STATS } from './modules/assembly_stats.nf'
include { MEDAKA; MEDAKA_STATS } from './modules/medaka.nf'
include { VIRSORTER2; VIRSORTER2_SUMMARY } from './modules/virsorter2.nf'
include { PLASMIDFINDER; MOBSUITE; PLASMID_SUMMARY } from './modules/plasmidfinder.nf'
include { PROKKA } from './modules/prokka.nf'
include { ABRICATE } from './modules/abricate.nf'
include { METABAT2 } from './modules/metabat2.nf'
include { CONCOCT } from './modules/concoct.nf'
include { CHECKM } from './modules/checkm.nf'
include { CHECKM as CHECKM_METABAT2 } from './modules/checkm.nf'
include { CHECKM as CHECKM_CONCOCT } from './modules/checkm.nf'
include { BIN_FILTER } from './modules/bin_filter.nf'
include { BIN_FILTER as BIN_FILTER_METABAT2 } from './modules/bin_filter.nf'
include { BIN_FILTER as BIN_FILTER_CONCOCT } from './modules/bin_filter.nf'
include { DREP } from './modules/drep.nf'
include { GTDBTK_CLASSIFY } from './modules/gtdbtk.nf'
include { KRAKEN2 } from './modules/kraken2.nf'
include { KRAKEN2 as KRAKEN2_METABAT2 } from './modules/kraken2.nf'
include { KRAKEN2 as KRAKEN2_CONCOCT } from './modules/kraken2.nf'
include { BRACKEN } from './modules/bracken.nf'
include { BRACKEN as BRACKEN_METABAT2 } from './modules/bracken.nf'
include { BRACKEN as BRACKEN_CONCOCT } from './modules/bracken.nf'
include { BRACKEN_COMBINED_REPORT } from './modules/bracken.nf'
include { PIPELINE_SUMMARY } from './modules/pipeline_summary.nf'

workflow {
    
    // Create input channel (search for FASTQ files in directory and subdirectories)
    // Pattern explanation:
    //   {input_dir}/*.{fastq,fastq.gz}    - files in root directory
    //   {input_dir}/**/*.{fastq,fastq.gz} - files in any subdirectory
    ont_reads_ch = Channel
        .fromPath([
            "${params.input_dir}/*.{fastq,fastq.gz}",
            "${params.input_dir}/**/*.{fastq,fastq.gz}"
        ], checkIfExists: false)  // Don't fail if pattern matches nothing
        .unique { it.getName() }  // Remove duplicates by filename
        .map { file ->
            def sample_id = file.getBaseName().replaceAll(/\.(fastq\.gz|fastq)$/, '')
            println "Found ONT sample: ${sample_id} with file: ${file}"
            return [sample_id, file]
        }
    // Log warning if no input files found (don't error - pipeline should complete successfully)
    ont_reads_ch.ifEmpty {
        log.warn "No FASTQ files found in ${params.input_dir} - pipeline will complete without processing"
    }
    
    // Stage 1: Quality Control with NanoPlot
    NANOPLOT(ont_reads_ch)
    
    // Stage 2: Read Filtering with Filtlong
    FILTLONG(ont_reads_ch)
    
    // Stage 3: De novo Assembly with Flye (using filtered reads)
    FLYE(FILTLONG.out.reads, params.flye_mode)
    
    // Stage 3.1: Medaka polishing (ONT-specific) - CRITICAL for gene accuracy!
    if (params.run_medaka) {
        // Combine Flye assembly with filtered reads for polishing
        medaka_input = FLYE.out.fasta.join(FILTLONG.out.reads, by: 0)
        MEDAKA(medaka_input)
        
        // Generate polishing statistics
        medaka_stats_input = FLYE.out.fasta.join(MEDAKA.out.polished_assembly, by: 0)
        MEDAKA_STATS(medaka_stats_input)
        
        // Use polished assembly for downstream analysis
        assembly_for_filtering = MEDAKA.out.polished_assembly
    } else {
        // Use Flye assembly directly (not recommended for ONT!)
        assembly_for_filtering = FLYE.out.fasta
    }
    
    // Stage 3.5: Filter contigs by minimum length
    FILTER_CONTIGS(assembly_for_filtering)
    
    // Stage 3.55: Viral sequence detection (optional - requires database)
    if (params.run_virsorter2 && params.virsorter2_db) {
        VIRSORTER2(FILTER_CONTIGS.out.filtered_assembly)
        VIRSORTER2_SUMMARY(VIRSORTER2.out.results)
    }
    
    // Stage 3.56: Plasmid detection (optional - requires database)
    if (params.run_plasmidfinder && params.plasmidfinder_db) {
        PLASMIDFINDER(FILTER_CONTIGS.out.filtered_assembly)
    }
    
    if (params.run_mobsuite) {
        MOBSUITE(FILTER_CONTIGS.out.filtered_assembly)
        
        // Combined plasmid summary if both methods run
        if (params.run_plasmidfinder && params.plasmidfinder_db) {
            plasmid_summary_input = PLASMIDFINDER.out.results.join(MOBSUITE.out.results, by: 0)
            PLASMID_SUMMARY(plasmid_summary_input)
        }
    }
    
    // Stage 3.6: Decompress filtered assembly for minimap2, PROKKA, ABRICATE, MetaBAT2, CONCOCT
    GUNZIP(FILTER_CONTIGS.out.filtered_assembly)

    // Stage 3.7: Map reads to filtered assembly with minimap2 (map-ont preset for ONT long reads)
    minimap2_input = GUNZIP.out.fasta.join(FILTLONG.out.reads, by: 0)
    MINIMAP2_MAPPING(minimap2_input)

    // Stage 3.8: Assembly statistics on filtered assembly
    ASSEMBLY_STATS(FILTER_CONTIGS.out.filtered_assembly)

    // Stage 4: Genome Binning with MetaBAT2 (using filtered contigs - unzipped for better compatibility)
    METABAT2(GUNZIP.out.fasta, MINIMAP2_MAPPING.out.bam)

    // Stage 5: Genome Binning with CONCOCT (using filtered contigs - unzipped)
    CONCOCT(GUNZIP.out.fasta, MINIMAP2_MAPPING.out.bam)
    
    // Stage 6: Quality Assessment with CheckM
    // Run CheckM on MetaBAT2 bins
    CHECKM_METABAT2(METABAT2.out.bins, "metabat2")
    
    // Run CheckM on CONCOCT bins  
    CHECKM_CONCOCT(CONCOCT.out.bins, "concoct")
    
    // Stage 6.5: Filter bins by quality (completeness >50%, contamination <10%)
    // Prepare input for BIN_FILTER: tuple(sample_id, bins, checkm_summary)
    metabat2_filter_input = METABAT2.out.bins
        .join(CHECKM_METABAT2.out.summary, by: 0)
    
    concoct_filter_input = CONCOCT.out.bins
        .join(CHECKM_CONCOCT.out.summary, by: 0)
    
    // Run quality filter on MetaBAT2 bins
    BIN_FILTER_METABAT2(metabat2_filter_input, "metabat2")
    
    // Run quality filter on CONCOCT bins
    BIN_FILTER_CONCOCT(concoct_filter_input, "concoct")
    
    // Stage 6.6: Dereplicate bins with dRep
    // Combine filtered bins from both binners for dereplication
    // Handle case where CONCOCT might fail/produce no bins
    drep_input = BIN_FILTER_METABAT2.out.filtered_bins
        .join(BIN_FILTER_CONCOCT.out.filtered_bins, by: 0, remainder: true)
        .map { sample_id, metabat2_bins, concoct_bins ->
            // If CONCOCT failed or produced no bins, use only MetaBAT2
            // Convert to list for consistency
            def metabat2_list = metabat2_bins instanceof List ? metabat2_bins : (metabat2_bins ? [metabat2_bins] : [])
            def concoct_list = concoct_bins instanceof List ? concoct_bins : (concoct_bins ? [concoct_bins] : [])
            
            // Combine bins from both methods
            def all_bins = metabat2_list + concoct_list
            
            // Only emit if we have bins
            if (all_bins.size() > 0) {
                return tuple(sample_id, all_bins)
            } else {
                return null
            }
        }
        .filter { it != null }  // Remove null entries (samples with no bins)
    
    DREP(drep_input)
    
    // Stage 6.7: Taxonomic classification with GTDB-Tk (optional - only if database available)
    if (params.gtdbtk_db) {
        GTDBTK_CLASSIFY(DREP.out.dereplicated_bins)
    }
    
    // Stage 7: Annotation on each bin after QC and dereplication
    // Flatten DEREPLICATED bins for per-bin annotation
    dereplicated_bins_for_annotation = DREP.out.dereplicated_bins
        .flatMap { sample_id, bins ->
            // bins is already a list of files
            def binList = bins instanceof List ? bins : [bins]
            binList.collect { bin ->
                // Skip placeholder files
                if (bin.getName().startsWith('.no_')) {
                    return null
                }
                def full_name = bin.getName().replaceAll('\\.fa$', '')
                // Skip empty bins
                if (bin.size() == 0) {
                    return null
                }
                // Keep full bin name (includes metabat2_ or concoct_ prefix from dRep)
                return tuple(sample_id, full_name, bin)
            }.findAll { it != null }
        }
    
    // Use dereplicated bins for all downstream annotation
    all_bins_for_annotation = dereplicated_bins_for_annotation
    
    // Stage 7.1: Genome annotation with Prokka on each bin
    PROKKA(all_bins_for_annotation)
    
    // Stage 7.2: AMR detection with ABRICATE on each bin
    ABRICATE(all_bins_for_annotation.map { sample_id, bin_name, bin -> tuple(bin_name, bin) }, 'card')

    // Stage 8: Taxonomic Classification with Kraken2 (optional - only if database provided)
    if (params.kraken2_db) {
        // Run Kraken2 on dereplicated bins
        KRAKEN2_METABAT2(METABAT2.out.bins, "metabat2")
        
        // Run Kraken2 on CONCOCT bins after CheckM
        KRAKEN2_CONCOCT(CONCOCT.out.bins, "concoct")
        
        // Stage 8: Species-level abundance estimation with Bracken (optional - only if database provided)
        if (params.bracken_db) {
            // Transform Kraken2 outputs for Bracken input format
            metabat2_bracken_input = KRAKEN2_METABAT2.out.kraken_reports
                .flatMap { method, reports ->
                    def reps = (reports instanceof java.util.List) ? reports : [reports]
                    reps.collect { report ->
                        def bin_id = report.getBaseName().replaceAll(/_kraken2_report\.txt$/, '')
                        [method, bin_id, report]
                    }
                }
            
            concoct_bracken_input = KRAKEN2_CONCOCT.out.kraken_reports
                .flatMap { method, reports ->
                    def reps = (reports instanceof java.util.List) ? reports : [reports]
                    reps.collect { report ->
                        def bin_id = report.getBaseName().replaceAll(/_kraken2_report\.txt$/, '')
                        [method, bin_id, report]
                    }
                }
            
            // Run Bracken on MetaBAT2 Kraken2 results
            BRACKEN_METABAT2(metabat2_bracken_input)
            
            // Run Bracken on CONCOCT Kraken2 results  
            BRACKEN_CONCOCT(concoct_bracken_input)
            
            // Create combined Bracken reports
            BRACKEN_COMBINED_REPORT(
                BRACKEN_METABAT2.out.bracken_output
                    .mix(BRACKEN_CONCOCT.out.bracken_output)
                    .map { method, bin_id, path -> tuple(method, path) }
                    .groupTuple(by: 0)
            )
        }
    }
    
    // ============================================
    // STAGE 8: PIPELINE SUMMARY GENERATION
    // ============================================
    // TEMPORARY DISABLED - causes pipeline timeout
    // TODO: Fix channel dependency issue
    // PIPELINE_SUMMARY must run AFTER all analyses complete
    // .collect() and .last() block when channel is empty
    // Need a barrier mechanism that avoids deadlock

    // ont_reads_ch
    //     .map { sample_id, reads -> tuple(sample_id, file("${params.outdir}")) }
    //     .set { results_ch }
    // PIPELINE_SUMMARY(results_ch)
}

// Print completion message
workflow.onComplete {
        def success = workflow?.success ?: false
        def exitStatus = workflow?.exitStatus ?: 0
        def failed = workflow?.stats?.failedCount ?: 0
        def outdir = params?.outdir ?: 'results'

        // Generate pipeline summary JSON after workflow completes
        if (failed == 0 && params.input_dir) {
            try {
                // Extract sample ID: parent of input/ (e.g. /work/SRR123/input → SRR123)
                def inputDir = new File(params.input_dir)
                def sampleId = (inputDir.getName() == 'input') ? inputDir.getParentFile()?.getName() : inputDir.getName()
                def summaryOutput = "${outdir}/00_summary/${sampleId}_summary.json"

                log.info "Generating pipeline summary for ${sampleId}..."

                def summaryCmd = [
                    'python3',
                    "${projectDir}/bin/generate_summary.py",
                    '--sample-id', sampleId,
                    '--results-dir', outdir,
                    '--output', summaryOutput
                ].execute()

                summaryCmd.waitForProcessOutput(System.out, System.err)

                if (summaryCmd.exitValue() == 0) {
                    log.info "✅ Pipeline summary generated: ${summaryOutput}"
                } else {
                    log.warn "⚠️ Failed to generate pipeline summary (exit code: ${summaryCmd.exitValue()})"
                }
            } catch (Exception e) {
                log.warn "⚠️ Error generating pipeline summary: ${e.message}"
            }
        }

        // Success = no failed processes
        if (failed == 0) {
            log.info """
            Pipeline completed successfully!
            
            Results structure:
            ${outdir}/
            ├── 01_QC/nanoplot/          # Quality control reports
            ├── 02_filtered/             # Filtered FASTQ files and logs
            ├── 03_assembly/             # Flye assembly results
            ├── 03_assembly/polished/    # Medaka polished assembly (ONT-corrected)
            ├── 04_binning/metabat2/     # MetaBAT2 binning results
            ├── 04_binning/concoct/      # CONCOCT binning results
            ├── 05_quality/metabat2/     # CheckM quality assessment (MetaBAT2 bins)
            ├── 05_quality/concoct/      # CheckM quality assessment (CONCOCT bins)
            ├── 05_filtered/metabat2/    # Quality-filtered bins (MetaBAT2)
            ├── 05_filtered/concoct/     # Quality-filtered bins (CONCOCT)
            ├── 05_drep/                 # Dereplicated representative genomes
            ├── 05_gtdbtk/               # GTDB-Tk taxonomy classification
            ├── 06_kraken2/metabat2/     # Kraken2 taxonomic classification (MetaBAT2 bins)
            ├── 06_kraken2/concoct/      # Kraken2 taxonomic classification (CONCOCT bins)
            ├── 07_bracken/metabat2/     # Bracken species-level abundance (MetaBAT2 bins)
            ├── 07_bracken/concoct/      # Bracken species-level abundance (CONCOCT bins)
            ├── 08_viruses/              # VirSorter2 viral sequence detection
            └── 09_plasmids/             # Plasmid detection (PlasmidFinder + MOB-suite)
            
            Assembly outputs:
            - ${outdir}/03_assembly/*.fasta.gz    # Final assembly
            - ${outdir}/03_assembly/*.gfa.gz      # Assembly graph
            - ${outdir}/03_assembly/*.info.txt    # Assembly statistics
            - ${outdir}/03_assembly/*.flye.log    # Assembly log
            
            Binning outputs:
            - ${outdir}/04_binning/metabat2/*_bins/    # MetaBAT2 bins
            - ${outdir}/04_binning/concoct/*_bins/     # CONCOCT bins
            
            Quality assessment outputs:
            - ${outdir}/05_quality/*/checkm_summary.tsv       # Bin quality summaries
            - ${outdir}/05_quality/*/checkm_results/          # Detailed CheckM results
            - ${outdir}/05_filtered/*/filter_report.txt       # Quality filtering reports
            - ${outdir}/05_filtered/*/filtered_bins/          # High-quality bins only
            - ${outdir}/05_drep/*/dereplicated_genomes/       # Representative genomes after dereplication
            - ${outdir}/05_drep/*/data_tables/                # dRep clustering and scoring data
            - ${outdir}/05_drep/*.log                         # dRep analysis logs
            - ${outdir}/05_gtdbtk/*/gtdbtk.*.summary.tsv      # GTDB-Tk taxonomy summary
            - ${outdir}/05_gtdbtk/*/classify/                 # GTDB-Tk detailed classification
            - ${outdir}/05_gtdbtk/*.log                       # GTDB-Tk analysis logs
            
            Taxonomic classification outputs:
            - ${outdir}/06_kraken2/*/metabat2_kraken2_summary.tsv    # MetaBAT2 bins taxonomy summary
            - ${outdir}/06_kraken2/*/concoct_kraken2_summary.tsv     # CONCOCT bins taxonomy summary
            - ${outdir}/06_kraken2/*/metabat2_kraken2_results/       # Detailed Kraken2 results (MetaBAT2)
            - ${outdir}/06_kraken2/*/concoct_kraken2_results/        # Detailed Kraken2 results (CONCOCT)
            
            Species-level abundance outputs:
            - ${outdir}/07_bracken/metabat2_bracken_combined_report.txt    # Combined MetaBAT2 species abundance
            - ${outdir}/07_bracken/concoct_bracken_combined_report.txt     # Combined CONCOCT species abundance
            - ${outdir}/07_bracken/metabat2/*_bracken_output.txt           # Individual MetaBAT2 bin abundances
            - ${outdir}/07_bracken/concoct/*_bracken_output.txt            # Individual CONCOCT bin abundances
            
            Next steps:
            - Review QC reports in ${outdir}/01_QC/nanoplot/
            - Check filtering logs in ${outdir}/02_filtered/
            - Examine assembly statistics in ${outdir}/03_assembly/*.info.txt
            - Analyze bin quality in ${outdir}/05_quality/*/checkm_summary.tsv
            - Check dereplication results in ${outdir}/05_drep/*/data_tables/Widb.csv
            - Review representative genomes in ${outdir}/05_drep/*/dereplicated_genomes/
            - Examine GTDB-Tk taxonomy in ${outdir}/05_gtdbtk/*/gtdbtk.*.summary.tsv
            - Review taxonomic assignments in ${outdir}/06_kraken2/*_kraken2_summary.tsv
            - Examine species-level abundances in ${outdir}/07_bracken/*_bracken_combined_report.txt
            - High-quality dereplicated bins are ready for further analysis
            """
        } else {
            log.error "Pipeline failed. Check the error messages above."
        }
}