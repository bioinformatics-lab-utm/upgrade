#!/bin/bash
# =============================================================================
# UPGRADE Platform - Automated Backup Script
# =============================================================================
# Performs daily backups of PostgreSQL, MinIO, and configuration files
# Usage: ./backup.sh [full|incremental|postgres|minio|config]
# Recommended: Run via cron at 2 AM daily
# =============================================================================

set -euo pipefail

# Configuration
BACKUP_ROOT="/home/upgrade/backups"
POSTGRES_CONTAINER="upgrade_postgres"
MINIO_CONTAINER="upgrade_minio"
RETENTION_DAYS=7
RETENTION_WEEKS=4
RETENTION_MONTHS=6

# AWS S3 for offsite backups (optional)
S3_BUCKET="${S3_BACKUP_BUCKET:-}"
AWS_PROFILE="${AWS_PROFILE:-default}"

# Notification
SLACK_WEBHOOK="${SLACK_BACKUP_WEBHOOK:-}"

# Timestamp
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DATE=$(date +%Y-%m-%d)
WEEKDAY=$(date +%u)
DAY_OF_MONTH=$(date +%d)

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $(date '+%Y-%m-%d %H:%M:%S') $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $(date '+%Y-%m-%d %H:%M:%S') $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $(date '+%Y-%m-%d %H:%M:%S') $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $(date '+%Y-%m-%d %H:%M:%S') $1"; }

# Send Slack notification
notify_slack() {
    local status=$1
    local message=$2
    
    if [[ -n "${SLACK_WEBHOOK}" ]]; then
        local color="good"
        local emoji=":white_check_mark:"
        
        if [[ "${status}" == "error" ]]; then
            color="danger"
            emoji=":x:"
        elif [[ "${status}" == "warning" ]]; then
            color="warning"
            emoji=":warning:"
        fi
        
        curl -s -X POST "${SLACK_WEBHOOK}" \
            -H 'Content-Type: application/json' \
            -d "{
                \"attachments\": [{
                    \"color\": \"${color}\",
                    \"title\": \"${emoji} UPGRADE Backup Report\",
                    \"text\": \"${message}\",
                    \"footer\": \"Backup System\",
                    \"ts\": $(date +%s)
                }]
            }" > /dev/null
    fi
}

# Create backup directories
setup_directories() {
    mkdir -p "${BACKUP_ROOT}/postgres/daily"
    mkdir -p "${BACKUP_ROOT}/postgres/weekly"
    mkdir -p "${BACKUP_ROOT}/postgres/monthly"
    mkdir -p "${BACKUP_ROOT}/minio/daily"
    mkdir -p "${BACKUP_ROOT}/config"
    mkdir -p "${BACKUP_ROOT}/logs"
}

# PostgreSQL backup
backup_postgres() {
    log_info "Starting PostgreSQL backup..."
    
    local backup_file="${BACKUP_ROOT}/postgres/daily/upgrade_db_${TIMESTAMP}.sql.gz"
    local start_time=$(date +%s)
    
    # Create backup with compression
    docker exec ${POSTGRES_CONTAINER} \
        pg_dump -U upgrade upgrade_db \
        --format=custom \
        --compress=6 \
        --verbose \
        2>> "${BACKUP_ROOT}/logs/postgres_${DATE}.log" \
        | gzip > "${backup_file}"
    
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    local size=$(du -h "${backup_file}" | cut -f1)
    
    # Verify backup
    if gzip -t "${backup_file}" 2>/dev/null; then
        log_success "PostgreSQL backup completed: ${backup_file} (${size}, ${duration}s)"
        
        # Weekly backup (Sunday)
        if [[ "${WEEKDAY}" == "7" ]]; then
            cp "${backup_file}" "${BACKUP_ROOT}/postgres/weekly/upgrade_db_week_$(date +%Y%W).sql.gz"
            log_info "Weekly backup created"
        fi
        
        # Monthly backup (1st of month)
        if [[ "${DAY_OF_MONTH}" == "01" ]]; then
            cp "${backup_file}" "${BACKUP_ROOT}/postgres/monthly/upgrade_db_month_$(date +%Y%m).sql.gz"
            log_info "Monthly backup created"
        fi
        
        echo "${backup_file}|${size}|${duration}"
    else
        log_error "PostgreSQL backup verification failed!"
        rm -f "${backup_file}"
        return 1
    fi
}

# MinIO backup (metadata and important buckets)
backup_minio() {
    log_info "Starting MinIO backup..."
    
    local backup_dir="${BACKUP_ROOT}/minio/daily/minio_${TIMESTAMP}"
    local start_time=$(date +%s)
    
    mkdir -p "${backup_dir}"
    
    # Use mc (MinIO client) to sync important buckets
    if command -v mc &> /dev/null; then
        # Configure mc alias if not exists
        mc alias set upgrade http://localhost:9000 ${MINIO_ROOT_USER} ${MINIO_ROOT_PASSWORD} 2>/dev/null || true
        
        # Backup genomic-gold bucket (final results)
        mc mirror upgrade/genomic-gold "${backup_dir}/genomic-gold" \
            --preserve \
            --remove \
            2>> "${BACKUP_ROOT}/logs/minio_${DATE}.log"
        
        log_success "MinIO gold bucket backed up"
    else
        # Fallback: Docker volume backup
        docker run --rm \
            -v upgrade_minio_data:/data \
            -v "${backup_dir}:/backup" \
            alpine \
            tar -czf /backup/minio_data.tar.gz -C /data .
        
        log_success "MinIO volume backed up"
    fi
    
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    local size=$(du -sh "${backup_dir}" | cut -f1)
    
    log_success "MinIO backup completed: ${backup_dir} (${size}, ${duration}s)"
    echo "${backup_dir}|${size}|${duration}"
}

# Configuration backup
backup_config() {
    log_info "Starting configuration backup..."
    
    local backup_file="${BACKUP_ROOT}/config/config_${TIMESTAMP}.tar.gz"
    local config_files=(
        "docker-compose.yml"
        "docker-compose.prod.yml"
        "nginx/"
        "monitoring/"
        "vault/config.hcl"
        "database/migrations/"
        "nextflow/nextflow.config"
        "nextflow/main.nf"
        ".env.example"
    )
    
    cd /home/upgrade
    
    tar -czf "${backup_file}" \
        --exclude="*.log" \
        --exclude="node_modules" \
        --exclude="__pycache__" \
        "${config_files[@]}" 2>/dev/null || true
    
    local size=$(du -h "${backup_file}" | cut -f1)
    log_success "Configuration backup completed: ${backup_file} (${size})"
    
    echo "${backup_file}|${size}|0"
}

# Upload to S3
upload_to_s3() {
    local file=$1
    
    if [[ -n "${S3_BUCKET}" ]] && command -v aws &> /dev/null; then
        log_info "Uploading to S3: ${file}"
        
        aws s3 cp "${file}" "s3://${S3_BUCKET}/backups/$(basename ${file})" \
            --profile "${AWS_PROFILE}" \
            --storage-class STANDARD_IA
        
        log_success "Uploaded to S3"
    fi
}

# Cleanup old backups
cleanup_old_backups() {
    log_info "Cleaning up old backups..."
    
    # Daily backups: keep for 7 days
    find "${BACKUP_ROOT}/postgres/daily" -name "*.sql.gz" -mtime +${RETENTION_DAYS} -delete
    find "${BACKUP_ROOT}/minio/daily" -type d -mtime +${RETENTION_DAYS} -exec rm -rf {} + 2>/dev/null || true
    
    # Weekly backups: keep for 4 weeks
    find "${BACKUP_ROOT}/postgres/weekly" -name "*.sql.gz" -mtime +$((RETENTION_WEEKS * 7)) -delete
    
    # Monthly backups: keep for 6 months
    find "${BACKUP_ROOT}/postgres/monthly" -name "*.sql.gz" -mtime +$((RETENTION_MONTHS * 30)) -delete
    
    # Config backups: keep for 30 days
    find "${BACKUP_ROOT}/config" -name "*.tar.gz" -mtime +30 -delete
    
    # Logs: keep for 14 days
    find "${BACKUP_ROOT}/logs" -name "*.log" -mtime +14 -delete
    
    log_success "Old backups cleaned up"
}

# Verify backup integrity
verify_backups() {
    log_info "Verifying backup integrity..."
    
    local errors=0
    
    # Check latest PostgreSQL backup
    local latest_pg=$(ls -t "${BACKUP_ROOT}/postgres/daily/"*.sql.gz 2>/dev/null | head -1)
    if [[ -n "${latest_pg}" ]]; then
        if gzip -t "${latest_pg}" 2>/dev/null; then
            log_success "PostgreSQL backup verified: $(basename ${latest_pg})"
        else
            log_error "PostgreSQL backup corrupted!"
            ((errors++))
        fi
    else
        log_warning "No PostgreSQL backup found"
        ((errors++))
    fi
    
    return ${errors}
}

# Generate backup report
generate_report() {
    local pg_result=$1
    local minio_result=$2
    local config_result=$3
    local total_duration=$4
    
    local report="*Backup Report - ${DATE}*\n\n"
    
    # Parse results
    IFS='|' read -r pg_file pg_size pg_duration <<< "${pg_result}"
    IFS='|' read -r minio_file minio_size minio_duration <<< "${minio_result}"
    IFS='|' read -r config_file config_size config_duration <<< "${config_result}"
    
    report+="*PostgreSQL:* ${pg_size} (${pg_duration}s)\n"
    report+="*MinIO:* ${minio_size} (${minio_duration}s)\n"
    report+="*Config:* ${config_size}\n"
    report+="\n*Total Duration:* ${total_duration}s\n"
    
    # Disk usage
    local disk_usage=$(df -h "${BACKUP_ROOT}" | tail -1 | awk '{print $5}')
    report+="*Backup Disk Usage:* ${disk_usage}\n"
    
    echo -e "${report}"
}

# Full backup
full_backup() {
    log_info "Starting full backup..."
    
    local start_time=$(date +%s)
    local errors=0
    
    setup_directories
    
    # PostgreSQL
    pg_result=$(backup_postgres) || ((errors++))
    
    # MinIO
    minio_result=$(backup_minio) || ((errors++))
    
    # Config
    config_result=$(backup_config) || ((errors++))
    
    # Upload to S3
    if [[ -n "${S3_BUCKET}" ]]; then
        upload_to_s3 "${pg_result%%|*}"
    fi
    
    # Cleanup
    cleanup_old_backups
    
    # Verify
    verify_backups || ((errors++))
    
    local end_time=$(date +%s)
    local total_duration=$((end_time - start_time))
    
    # Generate report
    local report=$(generate_report "${pg_result}" "${minio_result}" "${config_result}" "${total_duration}")
    
    if [[ ${errors} -eq 0 ]]; then
        log_success "Full backup completed successfully in ${total_duration}s"
        notify_slack "success" "${report}"
    else
        log_error "Backup completed with ${errors} errors"
        notify_slack "error" "Backup completed with ${errors} errors!\n\n${report}"
    fi
    
    return ${errors}
}

# Print usage
usage() {
    echo "UPGRADE Platform Backup Script"
    echo ""
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  full        Run full backup (PostgreSQL + MinIO + Config)"
    echo "  postgres    Backup PostgreSQL only"
    echo "  minio       Backup MinIO only"
    echo "  config      Backup configuration files only"
    echo "  verify      Verify existing backups"
    echo "  cleanup     Clean up old backups"
    echo "  restore     Restore from backup (interactive)"
    echo ""
    echo "Environment Variables:"
    echo "  S3_BACKUP_BUCKET    S3 bucket for offsite backups"
    echo "  SLACK_BACKUP_WEBHOOK  Slack webhook for notifications"
    echo ""
}

# Restore function
restore_postgres() {
    log_info "Available PostgreSQL backups:"
    ls -lh "${BACKUP_ROOT}/postgres/daily/"*.sql.gz 2>/dev/null | tail -10
    
    read -p "Enter backup filename to restore: " backup_file
    
    if [[ ! -f "${backup_file}" ]]; then
        log_error "Backup file not found: ${backup_file}"
        return 1
    fi
    
    log_warning "This will OVERWRITE the current database!"
    read -p "Are you sure? (yes/no): " confirm
    
    if [[ "${confirm}" != "yes" ]]; then
        log_info "Restore cancelled"
        return 0
    fi
    
    log_info "Restoring from: ${backup_file}"
    
    # Stop application
    docker-compose -f docker-compose.prod.yml stop web-backend rq-worker
    
    # Restore
    gunzip -c "${backup_file}" | docker exec -i ${POSTGRES_CONTAINER} \
        pg_restore -U upgrade -d upgrade_db --clean --if-exists
    
    # Start application
    docker-compose -f docker-compose.prod.yml start web-backend rq-worker
    
    log_success "Database restored successfully"
}

# Main
main() {
    case "${1:-full}" in
        full)
            full_backup
            ;;
        postgres)
            setup_directories
            backup_postgres
            ;;
        minio)
            setup_directories
            backup_minio
            ;;
        config)
            setup_directories
            backup_config
            ;;
        verify)
            verify_backups
            ;;
        cleanup)
            cleanup_old_backups
            ;;
        restore)
            restore_postgres
            ;;
        -h|--help|help)
            usage
            ;;
        *)
            echo "Unknown command: $1"
            usage
            exit 1
            ;;
    esac
}

main "$@"
