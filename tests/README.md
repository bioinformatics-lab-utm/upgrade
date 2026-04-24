# Testing Documentation

## Overview
Comprehensive test suite for the genomic analysis pipeline platform covering backend APIs, Nextflow modules, and integration workflows.

## Test Structure

```
tests/
├── backend/
│   ├── conftest.py              # Pytest fixtures
│   ├── test_utils.py            # Pipeline parsing utilities
│   ├── test_pipeline_summary.py # Pipeline summary tests
│   └── test_api_routes.py       # API endpoint tests
├── nextflow/
│   └── test_modules.py          # Nextflow module tests
├── integration/
│   └── test_workflow.py         # End-to-end workflow tests
└── requirements.txt             # Test dependencies
```

## Running Tests

### Install Test Dependencies
```bash
pip install -r tests/requirements.txt
```

### Run All Tests
```bash
pytest
```

### Run Specific Test Categories
```bash
# Backend tests only
pytest tests/backend/ -v

# Integration tests only
pytest tests/integration/ -v

# Nextflow module tests
pytest tests/nextflow/ -v
```

### Run with Coverage
```bash
pytest --cov=. --cov-report=html --cov-report=term
```

View coverage report:
```bash
open htmlcov/index.html
```

### Run Specific Test Files
```bash
# Test pipeline summary parsing
pytest tests/backend/test_pipeline_summary.py -v

# Test API routes
pytest tests/backend/test_api_routes.py -v

# Test workflow integration
pytest tests/integration/test_workflow.py -v
```

### Run Tests by Marker
```bash
# Run only unit tests
pytest -m unit

# Run only integration tests
pytest -m integration

# Skip slow tests
pytest -m "not slow"
```

## Test Categories

### Backend Tests (`tests/backend/`)

#### Pipeline Summary Tests (`test_pipeline_summary.py`)
Tests for parsing and generating pipeline summaries:
- ✅ NanoPlot QC parsing
- ✅ CheckM quality assessment
- ✅ ABRicate AMR detection
- ✅ Kraken2 taxonomy classification
- ✅ Assembly statistics parsing
- ✅ Quality score calculation
- ✅ Risk score calculation
- ✅ Recommendation generation
- ✅ Complete summary generation
- ✅ Error handling for missing files

**Example:**
```bash
pytest tests/backend/test_pipeline_summary.py::TestPipelineSummaryParser::test_parse_nanoplot_success -v
```

#### API Route Tests (`test_api_routes.py`)
Tests for backend API endpoints:
- ✅ Get pipeline summary by ID (integer)
- ✅ Get pipeline summary by sample name (string)
- ✅ List all pipelines
- ✅ Get pipeline status
- ✅ Cancel pipeline
- ✅ Upload FASTQ files
- ✅ List samples
- ✅ Delete samples
- ✅ Health checks
- ✅ Authentication
- ✅ Progress tracking

**Example:**
```bash
pytest tests/backend/test_api_routes.py::TestPipelineResultsAPI -v
```

### Nextflow Module Tests (`tests/nextflow/`)

Tests for individual Nextflow modules:
- ✅ Filtlong quality filtering
- ✅ NanoPlot QC
- ✅ Flye assembly
- ✅ CheckM quality assessment
- ✅ Kraken2 taxonomy
- ✅ ABRicate AMR detection
- ✅ Pipeline summary generation
- ✅ Configuration validation
- ✅ Input validation
- ✅ Output structure validation

**Example:**
```bash
pytest tests/nextflow/test_modules.py::TestNextflowModules::test_nanoplot_module -v
```

### Integration Tests (`tests/integration/`)

End-to-end workflow tests:
- ✅ Complete pipeline workflow (upload → process → results)
- ✅ Workflow with failures
- ✅ Concurrent pipeline execution
- ✅ Data validation
- ✅ MinIO integration
- ✅ Database integration
- ✅ Progress tracking
- ✅ Error recovery
- ✅ Graceful degradation

**Example:**
```bash
pytest tests/integration/test_workflow.py::TestFullPipelineWorkflow::test_complete_workflow -v
```

## Test Fixtures

### Database Fixtures (`conftest.py`)
- `mock_db_pool`: Mock asyncpg connection pool
- `event_loop`: Session-scoped asyncio event loop

### MinIO Fixtures
- `mock_minio_client`: Mock MinIO client

### File System Fixtures
- `temp_results_dir`: Temporary directory for test results
- `mock_fastq_file`: Generated FASTQ test data

### Result File Fixtures
- `mock_nanoplot_results`: Sample NanoStats.txt
- `mock_checkm_results`: Sample CheckM output
- `mock_abricate_results`: Sample ABRicate TSV
- `mock_kraken_results`: Sample Kraken2 kreport
- `mock_assembly_info`: Sample assembly_info.txt
- `sample_pipeline_summary`: Complete expected JSON structure

## Coverage Targets

| Component | Target | Current |
|-----------|--------|---------|
| Backend API | 80%+ | - |
| Pipeline Parsers | 90%+ | - |
| Nextflow Modules | 70%+ | - |
| Integration | 75%+ | - |

## Continuous Integration

Tests run automatically on GitHub Actions:
- **Backend Tests**: PostgreSQL + MinIO services
- **Integration Tests**: Full stack
- **Nextflow Tests**: With Nextflow installed
- **Linting**: flake8, black, isort

See `.github/workflows/tests.yml` for configuration.

## Writing New Tests

### Backend Test Template
```python
@pytest.mark.asyncio
async def test_new_feature(mock_db_pool):
    """Test description"""
    # Arrange
    mock_connection = AsyncMock()
    mock_db_pool.acquire.return_value.__aenter__.return_value = mock_connection
    
    # Act
    result = await your_function()
    
    # Assert
    assert result is not None
```

### Integration Test Template
```python
@pytest.mark.asyncio
@pytest.mark.integration
async def test_workflow_feature(mock_db_pool, mock_minio_client):
    """Test description"""
    # Setup
    # ... perform workflow steps
    
    # Verify
    assert expected_outcome
```

## Debugging Tests

### Run in Verbose Mode
```bash
pytest -vv -s
```

### Run with Debugging
```bash
pytest --pdb
```

### Show Print Statements
```bash
pytest -s
```

### Run Single Test
```bash
pytest tests/backend/test_pipeline_summary.py::TestPipelineSummaryParser::test_parse_nanoplot_success -v
```

## Common Issues

### Import Errors
Ensure you're in the project root:
```bash
cd /home/nicolaedrabcinski/upgrade
export PYTHONPATH=$PYTHONPATH:$(pwd)
pytest
```

### Async Test Failures
Ensure `pytest-asyncio` is installed and `asyncio_mode = auto` is in `pytest.ini`.

### Database Connection Issues
Mock all database calls in unit tests. Integration tests should use test databases only.

### File Permission Errors
Ensure temp directories are properly cleaned up using pytest fixtures.

## Performance Testing

### Run with Timing
```bash
pytest --durations=10
```

### Skip Slow Tests
```bash
pytest -m "not slow"
```

### Parallel Execution
```bash
pip install pytest-xdist
pytest -n auto
```

## Test Data

Test data is generated using fixtures. Real genomic data should NOT be committed to the repository.

### Generating Mock FASTQ
```python
@pytest.fixture
def mock_fastq_file(temp_results_dir):
    fastq_file = temp_results_dir / "test.fastq"
    with open(fastq_file, 'w') as f:
        for i in range(100):
            f.write(f"@read_{i}\n")
            f.write("ACGTACGTACGTACGT\n")
            f.write("+\n")
            f.write("IIIIIIIIIIIIIIII\n")
    return fastq_file
```

## Best Practices

1. **Use Fixtures**: Reuse setup code via pytest fixtures
2. **Mock External Services**: Don't rely on real databases/APIs in unit tests
3. **Test Edge Cases**: Include tests for errors, empty data, invalid inputs
4. **Keep Tests Fast**: Unit tests should run in milliseconds
5. **Descriptive Names**: Test names should describe what they're testing
6. **One Assert Per Test**: Prefer focused tests over complex multi-assert tests
7. **Clean Up**: Use fixtures and teardown to clean temporary files
8. **Document Complex Tests**: Add docstrings explaining non-obvious test logic

## Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
- [pytest-cov](https://pytest-cov.readthedocs.io/)
- [Testing Best Practices](https://docs.python-guide.org/writing/tests/)
