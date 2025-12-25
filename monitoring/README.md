# UPGRADE Monitoring Stack

Prometheus + Grafana monitoring for UPGRADE project.

## Services

### Prometheus
- **Port**: 9090
- **URL**: http://localhost:9090
- **Purpose**: Metrics collection and storage
- **Retention**: 30 days

### Grafana
- **Port**: 3000
- **URL**: http://localhost:3000
- **Default credentials**: admin / admin (change on first login)
- **Purpose**: Metrics visualization and dashboards

## Exporters

### PostgreSQL Exporter
- **Port**: 9187 (internal)
- **Metrics**: Database connections, query performance, table sizes

### Redis Exporter
- **Port**: 9121 (internal)
- **Metrics**: Memory usage, commands/sec, connected clients

### Node Exporter
- **Port**: 9100 (internal)
- **Metrics**: CPU, memory, disk, network usage

## Dashboards

### UPGRADE System Overview
Pre-configured dashboard showing:
- Pipeline runs status
- Database connections
- Redis memory usage
- MinIO storage usage
- System CPU usage

## Quick Start

1. Start monitoring stack:
```bash
docker-compose -f docker-compose.secrets.yml up -d prometheus grafana
```

2. Access Grafana:
```bash
open http://localhost:3000
```

3. View metrics in Prometheus:
```bash
open http://localhost:9090
```

## Custom Metrics

To add custom metrics to your Sanic backend:

```python
from prometheus_client import Counter, Histogram, generate_latest

# Define metrics
pipeline_runs = Counter('upgrade_pipeline_runs_total', 'Total pipeline runs')
pipeline_duration = Histogram('upgrade_pipeline_duration_seconds', 'Pipeline execution duration')

# In your route
@app.route('/api/pipeline/submit')
async def submit_pipeline(request):
    pipeline_runs.inc()
    # ... your code ...

# Add metrics endpoint
@app.route('/metrics')
async def metrics(request):
    return text(generate_latest())
```

## Useful Queries

### Database
```promql
# Active connections
pg_stat_activity_count

# Database size
pg_database_size_bytes{datname="upgrade_db"}
```

### Redis
```promql
# Memory usage
redis_memory_used_bytes

# Commands per second
rate(redis_commands_processed_total[1m])
```

### System
```promql
# CPU usage
100 - (avg by(instance) (irate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)

# Memory usage
node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes * 100
```

## Alerting (Future)

To add alerting:
1. Configure Alertmanager
2. Add alert rules to `prometheus.yml`
3. Configure notification channels (Slack, email, etc.)

Example alert rule:
```yaml
groups:
  - name: upgrade_alerts
    rules:
      - alert: HighDatabaseConnections
        expr: pg_stat_activity_count > 100
        for: 5m
        annotations:
          summary: "High number of database connections"
```

## Troubleshooting

### Prometheus not scraping targets
Check target status: http://localhost:9090/targets

### Grafana can't connect to Prometheus
Verify datasource configuration in Grafana settings

### Missing metrics
Check service logs:
```bash
docker logs upgrade_prometheus
docker logs upgrade_grafana
```
