# UPGRADE Project Tests

Comprehensive test suite for the UPGRADE (Urban Pathogen Genomic Surveillance Network) project.

## 📋 Test Coverage

### Test Files
- **conftest.py** - Pytest configuration and shared fixtures
- **test_auth_routes.py** - Authentication and authorization tests
- **test_pipeline_routes.py** - Pipeline management API tests
- **test_results_routes.py** - Results retrieval and analysis tests
- **test_database.py** - Database operations tests
- **test_utils.py** - Utility functions tests
- **test_fastq_validator.py** - FASTQ file validation tests
- **test_minio_helper.py** - MinIO storage operations tests
- **test_minio_integration.py** - MinIO integration tests

### Test Categories

#### Unit Tests (`@pytest.mark.unit`)
Fast tests with no external dependencies. Mock all external services.

```bash
./run_all_tests.sh unit
```

#### Integration Tests (`@pytest.mark.integration`)
Tests requiring external services (database, MinIO, Redis).

```bash
./run_all_tests.sh integration
```

#### Database Tests (`@pytest.mark.requires_db`)
Tests requiring PostgreSQL connection.

```bash
./run_all_tests.sh db
```

## 🚀 Running Tests

### Quick Start

```bash
# Run all tests with coverage
./run_all_tests.sh

# Run only unit tests
./run_all_tests.sh unit

# Run only integration tests
./run_all_tests.sh integration

# Run fast tests (exclude slow)
./run_all_tests.sh fast

# Run specific test file
pytest tests/test_pipeline_routes.py -v

# Run specific test class
pytest tests/test_pipeline_routes.py::TestPipelineRoutes -v

# Run specific test function
pytest tests/test_pipeline_routes.py::TestPipelineRoutes::test_get_pipeline_runs_empty -v
```

### With Docker

```bash
# Run tests inside backend container
docker exec -it upgrade_web_backend bash -c "cd /app && ./run_all_tests.sh"

# Run specific test type
docker exec -it upgrade_web_backend bash -c "cd /app && ./run_all_tests.sh unit"
```

## 📊 Coverage Report

After running tests with coverage, view the HTML report:

```bash
# Open coverage report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

Coverage reports are also generated in XML format (`coverage.xml`) for CI/CD integration.

## 🔧 Configuration

### pytest.ini
Main pytest configuration file with:
- Test discovery patterns
- Markers definitions
- Coverage settings
- Output options

### .coveragerc
Coverage tool configuration with:
- Source paths
- Exclusions
- Report format
- HTML output directory

### conftest.py
Shared fixtures and test utilities:
- Database connections
- Mock objects
- Test data
- Temporary directories

## 📝 Writing Tests

### Test Structure

```python
import pytest
from unittest.mock import Mock, AsyncMock

@pytest.mark.unit
class TestMyFeature:
    """Test my feature"""
    
    def test_basic_functionality(self):
        """Test basic functionality"""
        assert True
    
    @pytest.mark.asyncio
    async def test_async_functionality(self, db_conn):
        """Test async functionality"""
        result = await db_conn.fetchval("SELECT 1")
        assert result == 1
    
    def test_with_fixtures(self, temp_results_dir, sample_data):
        """Test using fixtures"""
        assert temp_results_dir.exists()
        assert 'sample_id' in sample_data
```

### Available Fixtures

- `db_pool` - Database connection pool
- `db_conn` - Single database connection
- `clean_db` - Clean database before test
- `temp_results_dir` - Temporary results directory
- `sample_summary_data` - Sample pipeline summary JSON
- `mock_minio_client` - Mock MinIO client
- `mock_sanic_app` - Mock Sanic application
- `mock_request` - Mock HTTP request
- `sample_fastq_content` - Sample FASTQ file content
- `sample_user_data` - Sample user registration data
- `sample_pipeline_params` - Sample pipeline parameters
- `test_sample` - Test sample in database
- `test_pipeline_run` - Test pipeline run in database
- `mock_redis_queue` - Mock Redis queue

## 🏷️ Test Markers

```python
# Mark test as unit test
@pytest.mark.unit

# Mark test as integration test
@pytest.mark.integration

# Mark test as slow
@pytest.mark.slow

# Mark test as requiring database
@pytest.mark.requires_db

# Mark test as requiring MinIO
@pytest.mark.requires_minio

# Mark test as requiring Redis
@pytest.mark.requires_redis
```

## 🔍 Debugging Tests

```bash
# Run with detailed output
pytest -vv

# Stop on first failure
pytest -x

# Show local variables in traceback
pytest -l

# Run last failed tests
pytest --lf

# Run failed tests first
pytest --ff

# Run with Python debugger
pytest --pdb
```

## ✅ Best Practices

1. **Test Isolation**: Each test should be independent
2. **Use Fixtures**: Reuse common setup via fixtures
3. **Mock External Services**: Don't rely on external APIs in unit tests
4. **Async Tests**: Use `@pytest.mark.asyncio` for async functions
5. **Clear Names**: Use descriptive test names
6. **Documentation**: Add docstrings to test classes and functions
7. **Assertions**: Use clear assertion messages
8. **Coverage**: Aim for >80% code coverage

## 📦 Dependencies

Testing dependencies in `requirements.txt`:
- pytest - Testing framework
- pytest-asyncio - Async test support
- pytest-sanic - Sanic framework support
- pytest-cov - Coverage reporting
- pytest-mock - Enhanced mocking
- coverage - Code coverage tool

## 🔄 Continuous Integration

Tests are designed to run in CI/CD pipelines:

```yaml
# Example GitHub Actions workflow
- name: Run tests
  run: |
    pip install -r requirements.txt
    ./run_all_tests.sh
    
- name: Upload coverage
  uses: codecov/codecov-action@v3
  with:
    file: ./coverage.xml
```

## 📈 Test Metrics

Current test statistics:
- **Total Tests**: ~100+
- **Unit Tests**: ~70+
- **Integration Tests**: ~30+
- **Target Coverage**: >80%

## 🆘 Troubleshooting

### Tests Fail to Import Modules
```bash
# Add current directory to Python path
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
```

### Database Connection Errors
```bash
# Set test database credentials
export TEST_DB_HOST=localhost
export TEST_DB_PORT=5432
export TEST_DB_NAME=upgrade_test_db
export TEST_DB_USER=upgrade
export TEST_DB_PASSWORD=upgrade
```

### Async Tests Timeout
```python
# Increase timeout in pytest.ini
[pytest]
asyncio_default_fixture_loop_scope = function
```

## 📚 Resources

- [pytest documentation](https://docs.pytest.org/)
- [pytest-asyncio documentation](https://pytest-asyncio.readthedocs.io/)
- [Coverage.py documentation](https://coverage.readthedocs.io/)
