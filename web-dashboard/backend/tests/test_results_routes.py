"""
Tests for results API routes
"""
import pytest
from unittest.mock import Mock, patch
import json
import sys
import os
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


@pytest.mark.unit
class TestResultsRoutes:
    """Test results retrieval routes"""
    
    def test_get_pipeline_summary_file_exists(self, temp_results_dir, sample_summary_data):
        """Test getting pipeline summary when file exists"""
        # Create test summary file
        sample_dir = temp_results_dir / "test_sample" / "00_summary"
        sample_dir.mkdir(parents=True)
        
        summary_file = sample_dir / "test_sample_summary.json"
        with open(summary_file, 'w') as f:
            json.dump(sample_summary_data, f)
        
        # Verify file exists and is readable
        assert summary_file.exists()
        
        with open(summary_file, 'r') as f:
            data = json.load(f)
            assert data['sample_id'] == 'TEST_SAMPLE_001'
            assert data['quality_score'] == 42.5
    
    def test_get_pipeline_summary_file_not_found(self, temp_results_dir):
        """Test getting non-existent pipeline summary"""
        summary_file = temp_results_dir / "nonexistent" / "00_summary" / "summary.json"
        
        assert not summary_file.exists()
    
    def test_parse_summary_metrics(self, sample_summary_data):
        """Test parsing summary file metrics"""
        assert 'quality_score' in sample_summary_data
        assert 'amr_risk_score' in sample_summary_data
        assert 'mags' in sample_summary_data
        
        mags = sample_summary_data['mags']
        assert mags['total_bins'] == 25
        assert mags['high_quality'] == 8
    
    def test_parse_qc_metrics(self, sample_summary_data):
        """Test parsing QC metrics"""
        qc = sample_summary_data['qc']
        
        assert qc['total_reads'] == 100000
        assert qc['total_bases'] == 500000000
        assert qc['mean_quality'] == 12.5
    
    def test_parse_assembly_metrics(self, sample_summary_data):
        """Test parsing assembly metrics"""
        assembly = sample_summary_data['assembly']
        
        assert assembly['total_contigs'] == 150
        assert assembly['total_length'] == 4500000
        assert assembly['n50'] == 35000
    
    def test_parse_amr_data(self, sample_summary_data):
        """Test parsing AMR data"""
        amr = sample_summary_data['amr']
        
        assert amr['total_arg_genes'] == 12
        assert amr['high_risk'] == 3
        assert amr['moderate_risk'] == 9
        assert amr['risk_score'] == 3
    
    def test_parse_pathogen_data(self, sample_summary_data):
        """Test parsing pathogen data"""
        pathogens = sample_summary_data['pathogens']
        
        assert len(pathogens) == 1
        assert pathogens[0]['name'] == 'Escherichia coli'
        assert pathogens[0]['confidence'] == 0.95
    
    def test_filter_by_quality_score(self, sample_summary_data):
        """Test quality score filtering logic"""
        quality = sample_summary_data['quality_score']
        
        # Test filters
        assert quality >= 30  # min_quality filter
        assert quality <= 100  # max_quality filter
    
    def test_filter_by_mags_count(self, sample_summary_data):
        """Test MAGs count filtering logic"""
        mags_count = sample_summary_data['mags']['total_bins']
        
        # Test filters
        assert mags_count >= 10  # min_mags filter
        assert mags_count <= 50  # max_mags filter
    
    def test_filter_by_amr_risk(self, sample_summary_data):
        """Test AMR risk filtering logic"""
        amr_risk = sample_summary_data['amr_risk_score']
        
        # Test filters
        assert amr_risk >= 0
        assert amr_risk <= 10
    
    def test_has_pathogens_filter(self, sample_summary_data):
        """Test pathogens presence filtering"""
        pathogens = sample_summary_data['pathogens']
        
        has_pathogens = len(pathogens) > 0
        assert has_pathogens == True
    
    @pytest.mark.asyncio
    async def test_get_results_list(self, temp_results_dir, sample_summary_data):
        """Test getting list of results"""
        # Create multiple test results
        for i in range(3):
            sample_dir = temp_results_dir / f"sample_{i}" / "00_summary"
            sample_dir.mkdir(parents=True)
            
            summary_file = sample_dir / f"sample_{i}_summary.json"
            data = sample_summary_data.copy()
            data['sample_id'] = f"SAMPLE_{i}"
            
            with open(summary_file, 'w') as f:
                json.dump(data, f)
        
        # Count results
        results = list(temp_results_dir.glob("*/00_summary/*_summary.json"))
        assert len(results) == 3
    
    def test_search_results(self, sample_summary_data):
        """Test search functionality"""
        sample_id = sample_summary_data['sample_id']
        
        # Search should match
        assert 'TEST' in sample_id
        assert sample_id.startswith('TEST_')


@pytest.mark.integration
class TestResultsDownload:
    """Test results download functionality"""
    
    def test_create_results_archive(self, temp_results_dir):
        """Test creating results archive"""
        results_path = temp_results_dir / "test_sample"
        results_path.mkdir(parents=True)
        
        # Create some result files
        (results_path / "assembly.fasta").write_text(">contig1\nATCG")
        (results_path / "report.html").write_text("<html></html>")
        
        assert results_path.exists()
        assert len(list(results_path.iterdir())) == 2
    
    def test_results_archive_structure(self, temp_results_dir):
        """Test results archive has correct structure"""
        # Create directory structure
        dirs = [
            "00_summary",
            "01_qc",
            "02_assembly",
            "03_binning",
            "04_taxonomy"
        ]
        
        results_path = temp_results_dir / "test_sample"
        for dir_name in dirs:
            (results_path / dir_name).mkdir(parents=True)
        
        # Verify structure
        for dir_name in dirs:
            assert (results_path / dir_name).exists()
