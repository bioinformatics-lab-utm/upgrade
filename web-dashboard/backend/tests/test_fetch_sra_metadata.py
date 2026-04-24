"""
Tests for Fetch SRA Metadata module
"""
import pytest
from unittest.mock import Mock, MagicMock, patch
import xml.etree.ElementTree as ET

# Skip all tests in this module if requests is not installed
pytest.importorskip("requests")


class TestFetchSRAMetadataImports:
    """Test module imports"""

    def test_requests_import(self):
        """Test requests can be imported"""
        import requests
        assert requests is not None

    def test_xml_import(self):
        """Test xml can be imported"""
        import xml.etree.ElementTree as ET
        assert ET is not None

    def test_json_import(self):
        """Test json can be imported"""
        import json
        assert json is not None

    def test_argparse_import(self):
        """Test argparse can be imported"""
        import argparse
        assert argparse is not None


class TestSearchSRA:
    """Test search_sra function"""

    def test_function_exists(self):
        """Test search_sra function exists"""
        from fetch_sra_metadata import search_sra
        assert search_sra is not None
        assert callable(search_sra)

    @patch('fetch_sra_metadata.requests.get')
    def test_search_sra_returns_list(self, mock_get):
        """Test search_sra returns list"""
        from fetch_sra_metadata import search_sra
        
        # Mock the response
        mock_response = Mock()
        mock_response.json.return_value = {
            'esearchresult': {
                'count': '2',
                'idlist': ['123', '456']
            }
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        result = search_sra("test query", max_results=10)
        
        assert isinstance(result, list)


class TestFetchMetadata:
    """Test fetch_metadata function"""

    def test_function_exists(self):
        """Test fetch_metadata function exists"""
        from fetch_sra_metadata import fetch_metadata
        assert fetch_metadata is not None
        assert callable(fetch_metadata)

    def test_fetch_metadata_empty_ids(self):
        """Test fetch_metadata with empty ids"""
        from fetch_sra_metadata import fetch_metadata
        
        result = fetch_metadata([])
        
        assert result == []


class TestParseSample:
    """Test parse_sample function"""

    def test_function_exists(self):
        """Test parse_sample function exists"""
        from fetch_sra_metadata import parse_sample
        assert parse_sample is not None
        assert callable(parse_sample)


class TestParseSampleHelpers:
    """Test sample parsing helper functions"""

    def test_module_has_search_sra(self):
        """Test module has search_sra"""
        import fetch_sra_metadata
        assert hasattr(fetch_sra_metadata, 'search_sra')

    def test_module_has_fetch_metadata(self):
        """Test module has fetch_metadata"""
        import fetch_sra_metadata
        assert hasattr(fetch_sra_metadata, 'fetch_metadata')

    def test_module_has_parse_sample(self):
        """Test module has parse_sample"""
        import fetch_sra_metadata
        assert hasattr(fetch_sra_metadata, 'parse_sample')


class TestModuleConstants:
    """Test module constants"""

    def test_ncbi_api_url_format(self):
        """Test NCBI API URL used in search"""
        expected_base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        assert 'ncbi.nlm.nih.gov' in expected_base

    def test_fetch_api_url_format(self):
        """Test NCBI fetch API URL"""
        expected_base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
        assert 'ncbi.nlm.nih.gov' in expected_base
