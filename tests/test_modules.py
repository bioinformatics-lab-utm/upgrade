"""
Unit tests for individual Nextflow modules
"""
import pytest
from pathlib import Path


class TestModuleNanoplot:
    """Test NANOPLOT module"""
    
    def test_module_exists(self):
        assert Path("nextflow/modules/nanoplot.nf").exists()
    
    def test_correct_container(self):
        with open("nextflow/modules/nanoplot.nf") as f:
            content = f.read()
        assert 'staphb/nanoplot' in content.lower()


class TestModuleFiltlong:
    """Test FILTLONG module"""
    
    def test_module_exists(self):
        assert Path("nextflow/modules/filtlong.nf").exists()
    
    def test_min_length_parameter(self):
        with open("nextflow/modules/filtlong.nf") as f:
            content = f.read()
        assert '--min_length' in content or 'min_length' in content


class TestModuleFlye:
    """Test FLYE module"""
    
    def test_module_exists(self):
        assert Path("nextflow/modules/flye.nf").exists()
    
    def test_meta_mode_support(self):
        with open("nextflow/modules/flye.nf") as f:
            content = f.read()
        assert '--meta' in content


class TestModuleProkka:
    """Test PROKKA module"""
    
    def test_module_exists(self):
        assert Path("nextflow/modules/prokka.nf").exists()
    
    def test_accepts_bin_tuple(self):
        with open("nextflow/modules/prokka.nf") as f:
            content = f.read()
        assert 'val(bin_name)' in content
    
    def test_output_includes_gff(self):
        with open("nextflow/modules/prokka.nf") as f:
            content = f.read()
        assert '.gff' in content and 'emit: gff' in content


class TestModuleAbricate:
    """Test ABRICATE module"""
    
    def test_module_exists(self):
        assert Path("nextflow/modules/abricate.nf").exists()
    
    def test_card_database_support(self):
        with open("nextflow/modules/abricate.nf") as f:
            content = f.read()
        assert 'card' in content.lower()


class TestModuleDeeparg:
    """Test DEEPARG module"""
    
    def test_module_exists(self):
        assert Path("nextflow/modules/deeparg.nf").exists()
    
    def test_custom_container(self):
        with open("nextflow/modules/deeparg.nf") as f:
            content = f.read()
        assert 'upgrade-deeparg' in content
    
    def test_database_path(self):
        with open("nextflow/modules/deeparg.nf") as f:
            content = f.read()
        assert '/deeparg_db' in content


class TestModuleMetabat2:
    """Test METABAT2 module"""
    
    def test_module_exists(self):
        assert Path("nextflow/modules/metabat2.nf").exists()
    
    def test_requires_bam_input(self):
        with open("nextflow/modules/metabat2.nf") as f:
            content = f.read()
        assert 'path(bam)' in content
    
    def test_outputs_bins(self):
        with open("nextflow/modules/metabat2.nf") as f:
            content = f.read()
        assert 'emit: bins' in content


class TestModuleConcoct:
    """Test CONCOCT module"""
    
    def test_module_exists(self):
        assert Path("nextflow/modules/concoct.nf").exists()
    
    def test_outputs_bins(self):
        with open("nextflow/modules/concoct.nf") as f:
            content = f.read()
        assert 'emit: bins' in content


class TestModuleCheckm:
    """Test CHECKM module"""
    
    def test_module_exists(self):
        assert Path("nextflow/modules/checkm.nf").exists()
    
    def test_accepts_bins_input(self):
        with open("nextflow/modules/checkm.nf") as f:
            content = f.read()
        # Should accept bins from METABAT2 or CONCOCT
        assert 'path' in content and 'bins' in content.lower()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
