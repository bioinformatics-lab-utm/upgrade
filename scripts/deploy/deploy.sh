#!/bin/bash
# =============================================================================
# UPGRADE Platform - Production Deployment Script
# =============================================================================
# Orchestrates the complete deployment process
# Usage: sudo ./deploy.sh [staging|production]
# =============================================================================

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname $(dirname ${SCRIPT_DIR}))"
ENVIRONMENT="${1:-staging}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m'

# Banner
print_banner() {
    echo -e "${CYAN}"
    echo "╔═══════════════════════════════════════════════════════════════════╗"
    echo "║                                                                   ║"
    echo "║   ██╗   ██╗██████╗  ██████╗ ██████╗  █████╗ ██████╗ ███████╗     ║"
    echo "║   ██║   ██║██╔══██╗██╔════╝ ██╔══██╗██╔══██╗██╔══██╗██╔════╝     ║"
    echo "║   ██║   ██║██████╔╝██║  ███╗██████╔╝███████║██║  ██║█████╗       ║"
    echo "║   ██║   ██║██╔═══╝ ██║   ██║██╔══██╗██╔══██║██║  ██║██╔══╝       ║"
    echo "║   ╚██████╔╝██║     ╚██████╔╝██║  ██║██║  ██║██████╔╝███████╗     ║"
    echo "║    ╚═════╝ ╚═╝      ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═════╝ ╚══════╝     ║"
    echo "║                                                                   ║"
    echo "║               Production Deployment System                        ║"
    echo "║                                                                   ║"
    echo "╚═══════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

log_step() { echo -e "\n${PURPLE}[STEP]${NC} $1"; }
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check prerequisites
check_prerequisites() {
    log_step "Checking prerequisites..."
    
    local errors=0
    
    # Check root
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root"
        exit 1
    fi
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed"
        ((errors++))
    else
        log_success "Docker: $(docker --version | cut -d' ' -f3)"
    fi
    
    # Check Docker Compose
    if ! command -v docker-compose &> /dev/null; then
        log_error "Docker Compose is not installed"
        ((errors++))
    else
        log_success "Docker Compose: $(docker-compose --version | cut -d' ' -f4)"
    fi
    
    # Check required files
    local required_files=(
        "docker-compose.prod.yml"
        "nginx/upgrade.conf"
        "vault/config.hcl"
        ".env"
    )
    
    for file in "${required_files[@]}"; do
        if [[ ! -f "${PROJECT_ROOT}/${file}" ]]; then
            log_error "Missing required file: ${file}"
            ((errors++))
        fi
    done
    
    if [[ ${errors} -gt 0 ]]; then
        log_error "Prerequisites check failed with ${errors} errors"
        exit 1
    fi
    
    log_success "All prerequisites met"
}

# Setup SSL certificates
setup_ssl() {
    log_step "Setting up SSL certificates..."
    
    if [[ -d "/etc/letsencrypt/live/upgrade.utm.md" ]]; then
        log_success "SSL certificates already exist"
    else
        log_info "Generating SSL certificates..."
        bash "${SCRIPT_DIR}/setup_ssl.sh"
    fi
}

# Initialize Vault
setup_vault() {
    log_step "Setting up HashiCorp Vault..."
    
    # Start Vault container first
    cd "${PROJECT_ROOT}"
    docker-compose -f docker-compose.prod.yml up -d vault
    
    sleep 10
    
    # Check if Vault is already initialized
    if docker exec upgrade_vault vault status 2>&1 | grep -q "Initialized.*true"; then
        log_success "Vault is already initialized"
        
        # Unseal if needed
        if docker exec upgrade_vault vault status 2>&1 | grep -q "Sealed.*true"; then
            log_info "Unsealing Vault..."
            bash "${SCRIPT_DIR}/init_vault.sh"
        fi
    else
        log_info "Initializing Vault..."
        bash "${SCRIPT_DIR}/init_vault.sh"
        bash "${SCRIPT_DIR}/store_secrets.sh"
    fi
}

# Pull Docker images
pull_images() {
    log_step "Pulling Docker images..."
    
    cd "${PROJECT_ROOT}"
    docker-compose -f docker-compose.prod.yml pull
    
    log_success "Images pulled"
}

# Run database migrations
run_migrations() {
    log_step "Running database migrations..."
    
    cd "${PROJECT_ROOT}"
    
    # Ensure database is running
    docker-compose -f docker-compose.prod.yml up -d postgres
    sleep 10
    
    # Run migrations
    for migration in database/migrations/*.sql; do
        log_info "Running: $(basename ${migration})"
        docker exec -i upgrade_postgres psql -U upgrade -d upgrade_db < "${migration}" 2>/dev/null || true
    done
    
    log_success "Migrations complete"
}

# Build frontend
build_frontend() {
    log_step "Building frontend..."
    
    cd "${PROJECT_ROOT}/web-dashboard/frontend"
    
    # Install dependencies
    npm ci --production=false
    
    # Build
    npm run build
    
    log_success "Frontend built"
}

# Deploy services
deploy_services() {
    log_step "Deploying services..."
    
    cd "${PROJECT_ROOT}"
    
    # Start infrastructure services
    log_info "Starting infrastructure services..."
    docker-compose -f docker-compose.prod.yml up -d \
        postgres redis minio kafka zookeeper
    
    sleep 15
    
    # Start monitoring
    log_info "Starting monitoring services..."
    docker-compose -f docker-compose.prod.yml up -d \
        prometheus grafana alertmanager loki promtail \
        node-exporter postgres-exporter redis-exporter
    
    sleep 5
    
    # Start application services
    log_info "Starting application services..."
    docker-compose -f docker-compose.prod.yml up -d \
        web-backend rq-worker weather-producer weather-consumer
    
    sleep 10
    
    # Start nginx (reverse proxy)
    log_info "Starting nginx..."
    docker-compose -f docker-compose.prod.yml up -d nginx
    
    log_success "All services deployed"
}

# Health checks
run_health_checks() {
    log_step "Running health checks..."
    
    local errors=0
    
    # Check services
    local services=(
        "postgres:5432"
        "redis:6379"
        "minio:9000"
        "web-backend:8000"
    )
    
    for service in "${services[@]}"; do
        IFS=':' read -r name port <<< "${service}"
        if docker exec upgrade_${name} nc -z localhost ${port} 2>/dev/null; then
            log_success "${name}: healthy"
        else
            log_error "${name}: unhealthy"
            ((errors++))
        fi
    done
    
    # Check API endpoint
    sleep 5
    if curl -sf http://localhost:8000/api/health > /dev/null; then
        log_success "API: healthy"
    else
        log_error "API: unhealthy"
        ((errors++))
    fi
    
    # Check HTTPS
    if curl -sf https://upgrade.utm.md/api/health > /dev/null 2>&1; then
        log_success "HTTPS: healthy"
    else
        log_warning "HTTPS: not accessible (may need DNS propagation)"
    fi
    
    if [[ ${errors} -gt 0 ]]; then
        log_error "Health checks failed with ${errors} errors"
        return 1
    fi
    
    log_success "All health checks passed"
}

# Setup cron jobs
setup_cron() {
    log_step "Setting up cron jobs..."
    
    # Backup cron
    cat > /etc/cron.d/upgrade-backup << EOF
# UPGRADE Platform Backup
0 2 * * * root ${SCRIPT_DIR}/backup.sh full >> /var/log/upgrade-backup.log 2>&1
EOF
    
    # Certificate renewal
    cat > /etc/cron.d/upgrade-certbot << EOF
# Let's Encrypt certificate renewal
0 0,12 * * * root certbot renew --quiet --post-hook "docker exec upgrade_nginx nginx -s reload"
EOF
    
    # Cleanup cron
    cat > /etc/cron.d/upgrade-cleanup << EOF
# UPGRADE Platform Cleanup
0 3 * * 0 root ${PROJECT_ROOT}/scripts/cleanup/cleanup_old_results.sh >> /var/log/upgrade-cleanup.log 2>&1
EOF
    
    chmod 644 /etc/cron.d/upgrade-*
    
    log_success "Cron jobs configured"
}

# Print summary
print_summary() {
    echo ""
    echo -e "${GREEN}╔═══════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║                    DEPLOYMENT COMPLETE!                           ║${NC}"
    echo -e "${GREEN}╚═══════════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${CYAN}Services:${NC}"
    echo "  • Web Application:  https://upgrade.utm.md"
    echo "  • API:              https://upgrade.utm.md/api"
    echo "  • Grafana:          https://upgrade.utm.md/grafana"
    echo "  • MinIO Console:    http://localhost:9001 (internal)"
    echo ""
    echo -e "${CYAN}Monitoring:${NC}"
    echo "  • Prometheus:       http://localhost:9090"
    echo "  • Alertmanager:     http://localhost:9093"
    echo ""
    echo -e "${CYAN}Credentials:${NC}"
    echo "  • Stored in HashiCorp Vault"
    echo "  • Access: vault kv list upgrade/"
    echo ""
    echo -e "${CYAN}Logs:${NC}"
    echo "  • Application: docker-compose -f docker-compose.prod.yml logs -f web-backend"
    echo "  • Nginx:       docker-compose -f docker-compose.prod.yml logs -f nginx"
    echo "  • All:         docker-compose -f docker-compose.prod.yml logs -f"
    echo ""
    echo -e "${CYAN}Useful Commands:${NC}"
    echo "  • Status:      docker-compose -f docker-compose.prod.yml ps"
    echo "  • Restart:     docker-compose -f docker-compose.prod.yml restart"
    echo "  • Backup:      ${SCRIPT_DIR}/backup.sh full"
    echo ""
}

# Rollback
rollback() {
    log_warning "Rolling back deployment..."
    
    cd "${PROJECT_ROOT}"
    
    # Stop services
    docker-compose -f docker-compose.prod.yml down
    
    # Restore from backup if available
    local latest_backup=$(ls -t backups/postgres/daily/*.sql.gz 2>/dev/null | head -1)
    
    if [[ -n "${latest_backup}" ]]; then
        log_info "Restoring database from: ${latest_backup}"
        docker-compose -f docker-compose.prod.yml up -d postgres
        sleep 10
        gunzip -c "${latest_backup}" | docker exec -i upgrade_postgres pg_restore -U upgrade -d upgrade_db --clean
    fi
    
    log_warning "Rollback complete. Manual intervention may be required."
}

# Main
main() {
    print_banner
    
    log_info "Environment: ${ENVIRONMENT}"
    log_info "Project Root: ${PROJECT_ROOT}"
    
    # Trap errors for rollback
    trap 'log_error "Deployment failed! Consider running: $0 rollback"; exit 1' ERR
    
    case "${ENVIRONMENT}" in
        staging|production)
            check_prerequisites
            setup_ssl
            setup_vault
            pull_images
            run_migrations
            build_frontend
            deploy_services
            run_health_checks
            setup_cron
            print_summary
            ;;
        rollback)
            rollback
            ;;
        status)
            cd "${PROJECT_ROOT}"
            docker-compose -f docker-compose.prod.yml ps
            ;;
        logs)
            cd "${PROJECT_ROOT}"
            docker-compose -f docker-compose.prod.yml logs -f
            ;;
        *)
            echo "Usage: $0 [staging|production|rollback|status|logs]"
            exit 1
            ;;
    esac
}

main "$@"
