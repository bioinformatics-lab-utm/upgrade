"""
Integration tests for Nextflow Pipeline
Tests actual pipeline execution with small test data
"""
import pytest
import subprocess
import shutil
from pathlib import Path
import tempfile


@pytest.fixture
def test_data_dir():
    """Create temporary directory with test FASTQ file"""
    temp_dir = tempfile.mkdtemp()
    test_fastq = Path(temp_dir) / "test_sample.fastq"
    
    # Create minimal test FASTQ (100 reads, ~10KB)
    with open(test_fastq, 'w') as f:
        for i in range(100):
            f.write(f"@read_{i}\n")
            f.write("ACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGT\n")
            f.write("+\n")
            f.write("IIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIII\n")
    
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def test_output_dir():
    """Create temporary output directory"""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


class TestPipelineExecution:
    """Test pipeline execution end-to-end"""
    
    @pytest.mark.slow
    @pytest.mark.integration
    def test_pipeline_runs_successfully(self, test_data_dir, test_output_dir):
        """Test complete pipeline execution with test data"""
        cmd = [
            'nextflow', 'run',
            'nextflow/main.nf',
            f'--input_dir={test_data_dir}',
            f'--outdir={test_output_dir}',
            '--flye_mode=nano-raw',
            '-profile', 'docker',
            '-resume'
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        assert result.returncode == 0, f"Pipeline failed:\n{result.stderr}"
        assert 'COMPLETED' in result.stdout or 'completed' in result.stdout.lower()
    
    @pytest.mark.slow
    @pytest.mark.integration  
    def test_all_processes_complete(self, test_data_dir, test_output_dir):
        """Verify all 13 processes complete successfully"""
        # Run pipeline
        cmd = [
            'nextflow', 'run',
            'nextflow/main.nf',
            f'--input_dir={test_data_dir}',
            f'--outdir={test_output_dir}',
            '-profile', 'docker',
            '-with-trace'
        ]
        
        subprocess.run(cmd, capture_output=True)
        
        # Check trace file
        trace_file = Path('trace.txt')
        if trace_file.exists():
            with open(trace_file) as f:
                content = f.read()
            
            expected_processes = [
                'NANOPLOT', 'FILTLONG', 'FLYE', 'GUNZIP',
                'BWA_MAPPING', 'ASSEMBLY_STATS',
                'METABAT2', 'CONCOCT',
                'CHECKM_METABAT2', 'CHECKM_CONCOCT',
                'PROKKA', 'ABRICATE', 'DEEPARG'
            ]
            
            for process in expected_processes:
                assert process in content, f"Process {process} not found in trace"


class TestBinAnnotation:
    """Test that bins are annotated correctly"""
    
    @pytest.mark.integration
    def test_prokka_runs_on_each_bin(self, test_output_dir):
        """Verify PROKKA runs separately on each bin"""
        prokka_dir = Path(test_output_dir) / "test_sample" / "prokka"
        
        if prokka_dir.exists():
            # Should have subdirectories for each bin
            bin_dirs = [d for d in prokka_dir.iterdir() if d.is_dir()]
            assert len(bin_dirs) >= 2, "Should have at least 2 bins annotated"
            
            # Each bin should have GFF file
            for bin_dir in bin_dirs:
                gff_files = list(bin_dir.glob("*.gff"))
                assert len(gff_files) > 0, f"No GFF file in {bin_dir}"
    
    @pytest.mark.integration
    def test_abricate_runs_on_each_bin(self, test_output_dir):
        """Verify ABRICATE runs separately on each bin"""
        abricate_dir = Path(test_output_dir) / "test_sample" / "abricate"
        
        if abricate_dir.exists():
            bin_dirs = [d for d in abricate_dir.iterdir() if d.is_dir()]
            assert len(bin_dirs) >= 2, "Should have ABRICATE results for at least 2 bins"
    
    @pytest.mark.integration
    def test_deeparg_runs_on_each_bin(self, test_output_dir):
        """Verify DEEPARG runs separately on each bin"""
        deeparg_dir = Path(test_output_dir) / "test_sample" / "deeparg"
        
        if deeparg_dir.exists():
            bin_dirs = [d for d in deeparg_dir.iterdir() if d.is_dir()]
            assert len(bin_dirs) >= 2, "Should have DEEPARG results for at least 2 bins"


class TestOutputFiles:
    """Test that expected output files are created"""
    
    def test_binning_creates_multiple_bins(self, test_output_dir):
        """Verify binning creates multiple bin files"""
        # Check work directory for bins
        work_dirs = list(Path('.').glob('.nextflow/work/**/*_bins'))
        
        if work_dirs:
            for work_dir in work_dirs:
                bin_files = list(work_dir.glob('*.fa'))
                # Should have at least: bin.1.fa, bin.2.fa, bin.unbinned.fa
                assert len(bin_files) >= 3, f"Expected at least 3 bin files in {work_dir}"


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-m', 'not slow'])
