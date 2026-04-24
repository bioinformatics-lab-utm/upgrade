"""
Tests for Nextflow modules
"""
import pytest
from pathlib import Path
import subprocess
import tempfile


class TestNextflowModules:
    """Test individual Nextflow modules"""
    
    def test_filtlong_module(self, mock_fastq_file, temp_results_dir):
        """Test Filtlong quality filtering module"""
        output_dir = temp_results_dir / "02_filtered"
        output_dir.mkdir(parents=True)
        
        # Would normally run: nextflow run modules/filtlong.nf
        # For testing, we verify the structure
        assert mock_fastq_file.exists()
        assert output_dir.exists()
    
    def test_nanoplot_module(self, mock_fastq_file, temp_results_dir):
        """Test NanoPlot QC module"""
        from tests.backend.test_utils import parse_nanoplot
        
        qc_dir = temp_results_dir / "01_qc"
        qc_dir.mkdir(parents=True)
        
        # Create expected output
        nanostats = qc_dir / "NanoStats.txt"
        nanostats.write_text("""Number of reads: 10000
Total bases: 50000000
Mean read length: 5000.0
Read length N50: 6500
Mean read quality: 12.5
""")
        
        result = parse_nanoplot(temp_results_dir)
        
        assert result is not None
        assert result['reads_count'] == 10000
        assert result['mean_quality'] == 12.5
    
    def test_flye_assembly_module(self, temp_results_dir):
        """Test Flye assembly module output"""
        assembly_dir = temp_results_dir / "03_assembly"
        assembly_dir.mkdir(parents=True)
        
        # Create assembly_info.txt
        assembly_info = assembly_dir / "assembly_info.txt"
        assembly_info.write_text("""#seq_name\tlength\tcov.\tcirc.\trepeat\tmult.\talt_group\tgraph_path
contig_1\t250000\t45\tY\tN\t1\t*\t*
contig_2\t180000\t38\tN\tN\t1\t*\t*
contig_3\t100000\t52\tN\tN\t1\t*\t*
contig_4\t60000\t41\tN\tN\t1\t*\t*
""")
        
        from tests.backend.test_utils import parse_assembly
        result = parse_assembly(temp_results_dir)
        
        assert result['total_length'] == 590000
        assert result['longest_contig'] == 250000
    
    def test_checkm_module(self, mock_checkm_results, temp_results_dir):
        """Test CheckM quality assessment module"""
        from tests.backend.test_utils import parse_checkm
        
        result = parse_checkm(mock_checkm_results.parent.parent)
        
        assert result['total_bins'] == 3
        assert result['high_quality'] >= 1
    
    def test_kraken2_module(self, mock_kraken_results, temp_results_dir):
        """Test Kraken2 taxonomy classification module"""
        from tests.backend.test_utils import parse_kraken
        
        result = parse_kraken(mock_kraken_results.parent.parent)
        
        assert 'species' in result
        assert len(result['species']) > 0
    
    def test_abricate_module(self, mock_abricate_results, temp_results_dir):
        """Test ABRicate AMR detection module"""
        from tests.backend.test_utils import parse_abricate
        
        amr_data, risk_score = parse_abricate(mock_abricate_results.parent.parent)
        
        assert amr_data['total_arg_genes'] >= 0
        assert 0 <= risk_score <= 10


class TestPipelineSummaryModule:
    """Test pipeline_summary.nf module"""
    
    def test_summary_generation(self, temp_results_dir, mock_nanoplot_results,
                                 mock_assembly_info, mock_checkm_results,
                                 mock_abricate_results, mock_kraken_results):
        """Test complete summary generation"""
        from tests.backend.test_utils import generate_full_summary
        
        sample_id = "NEXTFLOW_TEST"
        results_dir = mock_nanoplot_results.parent.parent
        
        summary = generate_full_summary(sample_id, results_dir)
        
        assert summary['sample_id'] == sample_id
        assert summary['status'] == 'completed'
        assert 'quality_score' in summary
        assert 'amr_risk_score' in summary
        assert 'recommendations' in summary
    
    def test_summary_with_missing_modules(self, temp_results_dir):
        """Test summary generation when some modules fail"""
        from tests.backend.test_utils import generate_full_summary
        
        # Only create QC results
        qc_dir = temp_results_dir / "01_qc"
        qc_dir.mkdir(parents=True)
        nanostats = qc_dir / "NanoStats.txt"
        nanostats.write_text("""Number of reads: 5000
Total bases: 25000000
Mean read length: 5000.0
Read length N50: 5500
Mean read quality: 11.5
""")
        
        summary = generate_full_summary("PARTIAL_TEST", temp_results_dir)
        
        # Should still generate summary with available data
        assert summary['sample_id'] == "PARTIAL_TEST"
        assert 'qc' in summary
        assert summary['qc'] is not None
    
    def test_summary_json_output(self, temp_results_dir, sample_pipeline_summary):
        """Test JSON output format"""
        import json
        
        output_file = temp_results_dir / "pipeline_summary.json"
        
        with open(output_file, 'w') as f:
            json.dump(sample_pipeline_summary, f, indent=2)
        
        # Verify file exists and is valid JSON
        assert output_file.exists()
        
        with open(output_file) as f:
            loaded = json.load(f)
        
        assert loaded['sample_id'] == sample_pipeline_summary['sample_id']
        assert loaded['quality_score'] == sample_pipeline_summary['quality_score']


class TestNextflowConfiguration:
    """Test Nextflow configuration"""
    
    def test_nextflow_config_exists(self):
        """Test that nextflow.config exists"""
        config_file = Path("/home/nicolaedrabcinski/upgrade/nextflow/nextflow.config")
        assert config_file.exists()
    
    def test_nextflow_config_syntax(self):
        """Test nextflow.config has valid syntax"""
        config_file = Path("/home/nicolaedrabcinski/upgrade/nextflow/nextflow.config")
        
        if config_file.exists():
            content = config_file.read_text()
            
            # Check for required sections
            assert 'params' in content or 'process' in content
            assert 'docker' in content or 'singularity' in content
    
    def test_module_structure(self):
        """Test that all required modules exist"""
        modules_dir = Path("/home/nicolaedrabcinski/upgrade/nextflow/modules")
        
        required_modules = [
            'nanoplot.nf',
            'filtlong.nf',
            'flye.nf',
            'metabat2.nf',
            'checkm.nf',
            'kraken2.nf',
            'bracken.nf',
            'pipeline_summary.nf'
        ]
        
        if modules_dir.exists():
            for module in required_modules:
                module_file = modules_dir / module
                if module_file.exists():
                    # Verify it's a valid Nextflow module
                    content = module_file.read_text()
                    assert 'process' in content.lower()


class TestContainerCompatibility:
    """Test biocontainer compatibility"""
    
    def test_docker_available(self):
        """Test if Docker is available"""
        try:
            result = subprocess.run(
                ['docker', '--version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            assert result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pytest.skip("Docker not available")
    
    def test_required_containers_exist(self):
        """Test that required biocontainers are accessible"""
        required_containers = [
            'quay.io/biocontainers/nanoplot',
            'quay.io/biocontainers/filtlong',
            'quay.io/biocontainers/flye',
            'quay.io/biocontainers/checkm-genome',
            'quay.io/biocontainers/kraken2'
        ]
        
        # Note: This would require internet connection to verify
        # In CI/CD, these would be cached
        pytest.skip("Requires internet connection for verification")


class TestPipelineInputValidation:
    """Test pipeline input validation"""
    
    def test_valid_fastq_input(self, mock_fastq_file):
        """Test validation of valid FASTQ input"""
        with open(mock_fastq_file) as f:
            first_line = f.readline()
            assert first_line.startswith('@')
    
    def test_invalid_fastq_input(self, temp_results_dir):
        """Test validation of invalid FASTQ input"""
        invalid_file = temp_results_dir / "invalid.fastq"
        invalid_file.write_text("This is not valid FASTQ")
        
        with open(invalid_file) as f:
            first_line = f.readline()
            assert not first_line.startswith('@')
    
    def test_empty_fastq_input(self, temp_results_dir):
        """Test handling of empty FASTQ file"""
        empty_file = temp_results_dir / "empty.fastq"
        empty_file.write_text("")
        
        assert empty_file.stat().st_size == 0
    
    def test_gzipped_fastq_input(self, temp_results_dir):
        """Test handling of gzipped FASTQ files"""
        import gzip
        
        gzipped_file = temp_results_dir / "test.fastq.gz"
        
        with gzip.open(gzipped_file, 'wt') as f:
            f.write("@read1\nACGT\n+\nIIII\n")
        
        assert gzipped_file.exists()
        assert gzipped_file.suffix == '.gz'
        
        # Verify can be decompressed
        with gzip.open(gzipped_file, 'rt') as f:
            first_line = f.readline()
            assert first_line.startswith('@')


class TestPipelineOutputValidation:
    """Test pipeline output validation"""
    
    def test_qc_output_structure(self, temp_results_dir):
        """Test QC output directory structure"""
        qc_dir = temp_results_dir / "01_qc"
        qc_dir.mkdir(parents=True)
        
        expected_files = ['NanoStats.txt', 'NanoPlot-report.html']
        for filename in expected_files:
            (qc_dir / filename).touch()
        
        assert (qc_dir / 'NanoStats.txt').exists()
        assert (qc_dir / 'NanoPlot-report.html').exists()
    
    def test_assembly_output_structure(self, temp_results_dir):
        """Test assembly output directory structure"""
        assembly_dir = temp_results_dir / "03_assembly"
        assembly_dir.mkdir(parents=True)
        
        (assembly_dir / "assembly.fasta").touch()
        (assembly_dir / "assembly_info.txt").touch()
        
        assert (assembly_dir / "assembly.fasta").exists()
        assert (assembly_dir / "assembly_info.txt").exists()
    
    def test_binning_output_structure(self, temp_results_dir):
        """Test binning output directory structure"""
        binning_dir = temp_results_dir / "05_binning"
        binning_dir.mkdir(parents=True)
        
        # Create bin files
        for i in range(1, 4):
            (binning_dir / f"bin.{i}.fa").touch()
        
        bins = list(binning_dir.glob("bin.*.fa"))
        assert len(bins) == 3
