# Changelog

All notable changes to the UPGRADE project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2025-01-21

### Performance
- Optimized CheckM process from 4 CPUs to 16 CPUs with increased memory
- Replaced console.log with development-only logger in frontend
- Added formatDate, formatDuration utilities to lib/utils.js
- Verified Redis caching working for /api/stations and /api/stats endpoints
- Verified async compression with run_in_executor pattern

### Code Quality
- Centralized format utilities (formatDate, formatDuration, formatSeconds, formatBytes)
- Frontend logging now uses logger module (silent in production)
- Test suite: 2237 tests passing, 31.20% coverage

### Documentation
- Updated BACKLOG with verification status for all items

## [0.9.0] - 2026-01-20

### Added
- Comprehensive security audit and fixes
- HashiCorp Vault integration for secrets management
- GitHub Actions CI/CD pipeline
- Prometheus/Grafana/Alertmanager monitoring stack
- Loki for log aggregation
- Error handling strategy in Nextflow pipeline
- LICENSE file (MIT)
- VERSION and CHANGELOG files
- React Error Boundary component
- pyrightconfig.json for IDE support

### Changed
- Rotated all compromised passwords in .env
- Added `.env` to .gitignore for security
- Closed open ports (0.0.0.0 → 127.0.0.1)
- Fixed hardcoded paths in Nextflow config (now uses UPGRADE_BASE_DIR env var)
- CONCOCT module now uses biocontainers image instead of runtime installation
- Added @protected decorator to upload endpoints
- Improved JWT secret handling (fail-fast in production)

### Fixed
- SQL injection vulnerabilities in scripts/queue_ont_samples.py and sync_minio_objects.py
- SQL syntax error in routes/samples.py (duplicated query)
- Hardcoded IP addresses in React frontend
- Import errors in administrative scripts (added pyrightconfig.json)

### Security
- [CRITICAL] Fixed SQL injection in admin scripts
- [CRITICAL] Added authentication to presigned-upload and confirm-upload endpoints
- [HIGH] Removed dangerous password fallbacks in config.py
- [HIGH] Added error strategies for Nextflow processes
- [MEDIUM] Centralized error handling to prevent information leakage

## [0.8.5] - 2026-01-15

### Added
- Data lineage tracking system
- Audit logging implementation
- Table partitioning for large tables
- dRep genome dereplication module
- GTDB-Tk taxonomy classification

### Changed
- Pipeline runtime reduced to 8 minutes
- CheckM optimization (3.75x faster)
- Lakehouse architecture (Bronze/Silver/Gold layers)

### Fixed
- Weather pipeline connection pooling
- Registration performance (30s → 300ms)
- Bare except clauses replaced with specific exceptions

## [0.8.0] - 2025-12-21

### Added
- JWT authentication system
- Rate limiting with Redis backend
- Bin quality filtering module
- Medaka polishing integration
- Real-time pipeline progress tracking

### Changed
- Moved secrets to environment variables
- Updated frontend to dynamic API URLs
- Improved error messages in API responses

### Fixed
- Email verification disabled (SMTP blocked)
- PostgreSQL connection pooling in Kafka producer
- Frontend deployment with external IP support

## [0.7.0] - 2025-12-01

### Added
- Initial Nextflow pipeline with 24 modules
- React dashboard for pipeline monitoring
- MinIO object storage integration
- Kafka for weather data streaming
- PostgreSQL with PostGIS extension

### Known Issues
- Hardcoded paths in Nextflow config
- No authentication on upload endpoints
- SQL injection vulnerabilities in scripts

---

For older versions, see git history.
