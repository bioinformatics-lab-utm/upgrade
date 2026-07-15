#!/bin/bash
# =============================================================================
# UPGRADE Platform - Store Secrets in Vault
# =============================================================================
# This script stores all application secrets in HashiCorp Vault
# Usage: sudo ./store_secrets.sh
# =============================================================================

set -euo pipefail

# Configuration
VAULT_CONTAINER="upgrade_vault"
SECRETS_DIR="/root/.vault-secrets"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check if running as root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root (use sudo)"
        exit 1
    fi
}

# Get root token
get_root_token() {
    if [[ ! -f "${SECRETS_DIR}/vault_keys.json" ]]; then
        log_error "Vault keys file not found. Run init_vault.sh first."
        exit 1
    fi
    
    ROOT_TOKEN=$(jq -r '.root_token' ${SECRETS_DIR}/vault_keys.json)
    export VAULT_TOKEN=${ROOT_TOKEN}
}

# Generate secure random password
generate_password() {
    openssl rand -base64 32 | tr -dc 'a-zA-Z0-9' | head -c 32
}

# Store a secret
store_secret() {
    local path=$1
    shift
    
    log_info "Storing secret: ${path}"
    docker exec -e VAULT_TOKEN=${VAULT_TOKEN} ${VAULT_CONTAINER} \
        vault kv put upgrade/${path} "$@"
}

# Store PostgreSQL credentials
store_postgres_secrets() {
    log_info "Storing PostgreSQL secrets..."
    
    # Generate password if not provided
    POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-$(generate_password)}
    
    store_secret postgres \
        host=postgres \
        port=5432 \
        database=upgrade_db \
        username=upgrade \
        password=${POSTGRES_PASSWORD}
    
    # Store replication credentials
    REPLICATION_PASSWORD=$(generate_password)
    store_secret postgres/replication \
        username=replicator \
        password=${REPLICATION_PASSWORD}
    
    log_success "PostgreSQL secrets stored"
    echo "POSTGRES_PASSWORD=${POSTGRES_PASSWORD}" >> ${SECRETS_DIR}/generated_passwords.txt
}

# Store Redis credentials
store_redis_secrets() {
    log_info "Storing Redis secrets..."
    
    REDIS_PASSWORD=${REDIS_PASSWORD:-$(generate_password)}
    
    store_secret redis \
        password=${REDIS_PASSWORD}
    
    log_success "Redis secrets stored"
    echo "REDIS_PASSWORD=${REDIS_PASSWORD}" >> ${SECRETS_DIR}/generated_passwords.txt
}

# Store MinIO credentials
store_minio_secrets() {
    log_info "Storing MinIO secrets..."
    
    MINIO_ROOT_USER=${MINIO_ROOT_USER:-upgrade_minio}
    MINIO_ROOT_PASSWORD=${MINIO_ROOT_PASSWORD:-$(generate_password)}
    
    store_secret minio \
        access_key=${MINIO_ROOT_USER} \
        secret_key=${MINIO_ROOT_PASSWORD}
    
    log_success "MinIO secrets stored"
    echo "MINIO_ROOT_USER=${MINIO_ROOT_USER}" >> ${SECRETS_DIR}/generated_passwords.txt
    echo "MINIO_ROOT_PASSWORD=${MINIO_ROOT_PASSWORD}" >> ${SECRETS_DIR}/generated_passwords.txt
}

# Store JWT secrets
store_jwt_secrets() {
    log_info "Storing JWT secrets..."
    
    JWT_SECRET=$(openssl rand -base64 64 | tr -d '\n')
    JWT_REFRESH_SECRET=$(openssl rand -base64 64 | tr -d '\n')
    
    store_secret jwt \
        secret="${JWT_SECRET}" \
        refresh_secret="${JWT_REFRESH_SECRET}" \
        algorithm=HS256 \
        expiry=3600 \
        refresh_expiry=604800
    
    log_success "JWT secrets stored"
}

# Store SMTP credentials
store_smtp_secrets() {
    log_info "Storing SMTP secrets..."
    
    read -p "Enter SMTP host [smtp.gmail.com]: " SMTP_HOST
    SMTP_HOST=${SMTP_HOST:-smtp.gmail.com}
    
    read -p "Enter SMTP port [587]: " SMTP_PORT
    SMTP_PORT=${SMTP_PORT:-587}
    
    read -p "Enter SMTP username: " SMTP_USERNAME
    
    read -s -p "Enter SMTP password: " SMTP_PASSWORD
    echo ""
    
    store_secret smtp \
        host=${SMTP_HOST} \
        port=${SMTP_PORT} \
        username=${SMTP_USERNAME} \
        password=${SMTP_PASSWORD} \
        from_email="noreply@upgrade.utm.md" \
        from_name="UPGRADE Platform"
    
    log_success "SMTP secrets stored"
}

# Store Grafana credentials
store_grafana_secrets() {
    log_info "Storing Grafana secrets..."
    
    GRAFANA_ADMIN_USER=${GRAFANA_ADMIN_USER:-admin}
    GRAFANA_ADMIN_PASSWORD=${GRAFANA_ADMIN_PASSWORD:-$(generate_password)}
    
    store_secret grafana \
        admin_user=${GRAFANA_ADMIN_USER} \
        admin_password=${GRAFANA_ADMIN_PASSWORD}
    
    log_success "Grafana secrets stored"
    echo "GRAFANA_ADMIN_USER=${GRAFANA_ADMIN_USER}" >> ${SECRETS_DIR}/generated_passwords.txt
    echo "GRAFANA_ADMIN_PASSWORD=${GRAFANA_ADMIN_PASSWORD}" >> ${SECRETS_DIR}/generated_passwords.txt
}

# Store Sentry DSN
store_sentry_secrets() {
    log_info "Storing Sentry configuration..."
    
    read -p "Enter Sentry DSN (or press Enter to skip): " SENTRY_DSN
    
    if [[ -n "${SENTRY_DSN}" ]]; then
        store_secret sentry \
            dsn=${SENTRY_DSN}
        log_success "Sentry secrets stored"
    else
        log_warning "Sentry DSN skipped"
    fi
}

# Store API keys
store_api_keys() {
    log_info "Storing API keys..."
    
    # Internal API key for service-to-service communication
    INTERNAL_API_KEY=$(openssl rand -hex 32)
    
    # Webhook signing key
    WEBHOOK_SECRET=$(openssl rand -hex 32)
    
    store_secret api_keys \
        internal_api_key=${INTERNAL_API_KEY} \
        webhook_secret=${WEBHOOK_SECRET}
    
    log_success "API keys stored"
}

# Generate .env file for production
generate_env_file() {
    log_info "Generating production .env file..."
    
    APP_TOKEN=$(cat ${SECRETS_DIR}/app_token.txt)
    
    cat > ${SECRETS_DIR}/production.env << EOF
# =============================================================================
# UPGRADE Platform - Production Environment Variables
# =============================================================================
# Generated: $(date)
# WARNING: This file contains sensitive information
# =============================================================================

# Environment
ENV=production
DEBUG=false
DOMAIN=upgrade.utm.md

# Vault Configuration
VAULT_ADDR=http://vault:8200
VAULT_TOKEN=${APP_TOKEN}

# Database (passwords in Vault)
POSTGRES_USER=upgrade
POSTGRES_DB=upgrade_db
POSTGRES_PASSWORD=$(grep POSTGRES_PASSWORD ${SECRETS_DIR}/generated_passwords.txt | cut -d= -f2)

# Redis (password in Vault)
REDIS_PASSWORD=$(grep REDIS_PASSWORD ${SECRETS_DIR}/generated_passwords.txt | cut -d= -f2)

# MinIO (credentials in Vault)
MINIO_ROOT_USER=$(grep MINIO_ROOT_USER ${SECRETS_DIR}/generated_passwords.txt | cut -d= -f2)
MINIO_ROOT_PASSWORD=$(grep MINIO_ROOT_PASSWORD ${SECRETS_DIR}/generated_passwords.txt | cut -d= -f2)

# Grafana
GRAFANA_ADMIN_USER=$(grep GRAFANA_ADMIN_USER ${SECRETS_DIR}/generated_passwords.txt | cut -d= -f2)
GRAFANA_ADMIN_PASSWORD=$(grep GRAFANA_ADMIN_PASSWORD ${SECRETS_DIR}/generated_passwords.txt | cut -d= -f2)

# Sentry (optional)
SENTRY_DSN=

# Docker Image Tag
IMAGE_TAG=latest
EOF
    
    chmod 600 ${SECRETS_DIR}/production.env
    
    log_success "Production .env file generated at ${SECRETS_DIR}/production.env"
}

# List all secrets
list_secrets() {
    log_info "Listing all stored secrets..."
    
    docker exec -e VAULT_TOKEN=${VAULT_TOKEN} ${VAULT_CONTAINER} \
        vault kv list upgrade/
}

# Print summary
print_summary() {
    echo ""
    echo "============================================================"
    echo -e "${GREEN}Secrets Storage Complete!${NC}"
    echo "============================================================"
    echo ""
    echo "Secrets stored in Vault:"
    list_secrets
    echo ""
    echo "Generated files:"
    echo "  - ${SECRETS_DIR}/generated_passwords.txt"
    echo "  - ${SECRETS_DIR}/production.env"
    echo ""
    echo "Next Steps:"
    echo "  1. Copy ${SECRETS_DIR}/production.env to /home/upgrade/.env"
    echo "  2. Secure backup generated_passwords.txt"
    echo "  3. Start services: docker-compose -f docker-compose.prod.yml up -d"
    echo ""
}

# Main execution
main() {
    echo ""
    echo "============================================================"
    echo "  UPGRADE Platform - Store Secrets in Vault"
    echo "============================================================"
    echo ""
    
    check_root
    get_root_token
    
    # Initialize password file
    echo "# Generated Passwords - $(date)" > ${SECRETS_DIR}/generated_passwords.txt
    chmod 600 ${SECRETS_DIR}/generated_passwords.txt
    
    store_postgres_secrets
    store_redis_secrets
    store_minio_secrets
    store_jwt_secrets
    store_grafana_secrets
    store_api_keys
    
    # Optional secrets
    read -p "Configure SMTP for email notifications? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        store_smtp_secrets
    fi
    
    read -p "Configure Sentry for error tracking? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        store_sentry_secrets
    fi
    
    generate_env_file
    print_summary
}

main "$@"
