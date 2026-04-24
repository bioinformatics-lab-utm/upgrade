"""
Tests for Pipeline Monitoring Routes
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch


class TestMonitoringBlueprintSetup:
    """Tests for monitoring blueprint configuration"""

    def test_monitoring_bp_import(self):
        """Test monitoring blueprint can be imported"""
        from routes.pipeline_monitoring import monitoring_bp
        assert monitoring_bp is not None

    def test_blueprint_name(self):
        """Test blueprint name"""
        from routes.pipeline_monitoring import monitoring_bp
        assert monitoring_bp.name == 'monitoring'

    def test_blueprint_url_prefix(self):
        """Test blueprint URL prefix"""
        from routes.pipeline_monitoring import monitoring_bp
        assert monitoring_bp.url_prefix == '/api/monitoring'


class TestMonitoringRouteImports:
    """Tests for monitoring route imports"""

    def test_sanic_blueprint_type(self):
        """Test monitoring_bp is Sanic Blueprint"""
        from routes.pipeline_monitoring import monitoring_bp
        from sanic import Blueprint
        assert isinstance(monitoring_bp, Blueprint)

    def test_module_exists(self):
        """Test module can be imported"""
        from routes import pipeline_monitoring
        assert pipeline_monitoring is not None
