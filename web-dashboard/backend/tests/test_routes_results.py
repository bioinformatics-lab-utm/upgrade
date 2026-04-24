"""
Tests for Results Routes
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch


class TestResultsBlueprintSetup:
    """Tests for results blueprint configuration"""

    def test_results_bp_import(self):
        """Test results blueprint can be imported"""
        from routes.results import results_bp
        assert results_bp is not None

    def test_blueprint_name(self):
        """Test blueprint name"""
        from routes.results import results_bp
        assert results_bp.name == 'results'

    def test_blueprint_url_prefix(self):
        """Test blueprint URL prefix"""
        from routes.results import results_bp
        assert results_bp.url_prefix == '/api/pipeline/results'


class TestResultsRouteImports:
    """Tests for results route imports"""

    def test_sanic_blueprint_type(self):
        """Test results_bp is Sanic Blueprint"""
        from routes.results import results_bp
        from sanic import Blueprint
        assert isinstance(results_bp, Blueprint)

    def test_module_exists(self):
        """Test module can be imported"""
        from routes import results
        assert results is not None
