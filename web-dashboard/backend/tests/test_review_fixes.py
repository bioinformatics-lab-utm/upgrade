"""
Regression tests for bugs found in the 2026-10-16 review:
ABRicate column mapping, results file access confined to the run's directory
"""
import importlib.util
import json
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch

import pytest

HEADER = ("#FILE\tSEQUENCE\tSTART\tEND\tSTRAND\tGENE\tCOVERAGE\tCOVERAGE_MAP\tGAPS\t%COVERAGE\t"
          "%IDENTITY\tDATABASE\tACCESSION\tPRODUCT\tRESISTANCE\n")
ROW = ("bin.fa\tcontig_2\t29379\t29827\t-\tPC1_beta-lactamase_(blaZ)\t1-448/846\t===\t2/3\t52.84\t"
       "96.89\tcard\tCP000732.1\tThe blaZ beta-lactamase\tpenam;cephalosporin\n")


def _generate_summary():
    path = Path(__file__).resolve().parents[3] / 'nextflow' / 'bin' / 'generate_summary.py'
    spec = importlib.util.spec_from_file_location('generate_summary', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestParseAbricate:
    def test_columns_mapped_by_header(self, tmp_path):
        """Test %IDENTITY / %COVERAGE / RESISTANCE come from the right columns"""
        bin_dir = tmp_path / '07_amr' / 'abricate' / 'bin.1'
        bin_dir.mkdir(parents=True)
        (bin_dir / 'bin_abricate_card.tab').write_text(HEADER + ROW)

        amr, risk = _generate_summary().parse_abricate(str(tmp_path))

        gene = amr['genes'][0]
        assert (gene['identity'], gene['coverage']) == (96.89, 52.84)
        assert gene['antibiotic_class'] == 'penam'
        assert gene['risk_level'] == 'high'
        assert gene['database'] == 'ABRicate/card'
        assert amr['high_risk_genes'] == 1 and risk == 0.5

    def test_summary_matrix_ignored(self, tmp_path):
        """Test the abricate --summary matrix is not read as genes"""
        bin_dir = tmp_path / '07_amr' / 'abricate' / 'bin.1'
        bin_dir.mkdir(parents=True)
        (bin_dir / 'bin_abricate_card_summary.txt').write_text(
            "#FILE\tNUM_FOUND\tA\tB\nbin.fa\t2\t100.00\t52.84\n")

        amr, _ = _generate_summary().parse_abricate(str(tmp_path))

        assert amr['total_genes'] == 0


class TestResultFileAccess:
    @pytest.mark.asyncio
    @pytest.mark.parametrize('handler', ['view_file', 'download_file'])
    async def test_path_cannot_leave_run_directory(self, tmp_path, handler):
        """Test ../ cannot reach another run's directory under the results root"""
        from auth import generate_token
        import routes.results as results

        (tmp_path / 'mine').mkdir()
        (tmp_path / 'theirs').mkdir()
        (tmp_path / 'theirs' / 'secret.txt').write_text('other user data')

        request = Mock()
        request.headers = {"Authorization": f"Bearer {generate_token(user_id=7, username='u', email='u@x.io')}"}
        request.ctx = Mock()
        request.args = {'path': '../theirs/secret.txt'}

        with patch.object(results, 'RESULTS_DIR', tmp_path), \
             patch.object(results, 'user_owns_run_ref', new=AsyncMock(return_value=True)):
            acquire = Mock()
            acquire.__aenter__ = AsyncMock(return_value=AsyncMock())
            acquire.__aexit__ = AsyncMock(return_value=False)
            request.app.ctx.db_pool.acquire = Mock(return_value=acquire)
            response = await getattr(results, handler)(request, 'mine')

        assert response.status == 403
