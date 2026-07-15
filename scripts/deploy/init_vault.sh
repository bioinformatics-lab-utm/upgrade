#!/bin/bash
# =============================================================================
# UPGRADE Platform - Vault Initialization Script
# =============================================================================
# This script initializes HashiCorp Vault and stores the unseal keys securely
# Usage: sudo ./init_vault.sh
# =============================================================================

set -euo pipefail

# Configuration
VAULT_CONTAINER="upgrade_vault"
VAULT_ADDR="http://localhost:8200"
KEY_SHARES=5
KEY_THRESHOLD=3
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

# Wait for Vault to be ready
wait_for_vault() {
    log_info "Waiting for Vault to be ready..."
    
    for i in {1..30}; do
        if docker exec ${VAULT_CONTAINER} vault status 2>/dev/null | grep -q "Initialized"; then
            return 0
        fi
        sleep 2
    done
    
    log_error "Vault did not become ready in time"
    exit 1
}

# Check if Vault is already initialized
check_initialized() {
    if docker exec ${VAULT_CONTAINER} vault status 2>&1 | grep -q "Initialized.*true"; then
        log_warning "Vault is already initialized"
        
        if [[ -f "${SECRETS_DIR}/vault_keys.json" ]]; then
            log_info "Found existing keys at ${SECRETS_DIR}/vault_keys.json"
            read -p "Do you want to unseal with existing keys? (Y/n): " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Nn]$ ]]; then
                unseal_vault
                return 1
            fi
        fi
        
        log_error "No keys found. Manual intervention required."
        exit 1
    fi
    return 0
}

# Initialize Vault
initialize_vault() {
    log_info "Initializing Vault with ${KEY_SHARES} key shares, ${KEY_THRESHOLD} threshold..."
    
    # Create secrets directory
    mkdir -p ${SECRETS_DIR}
    chmod 700 ${SECRETS_DIR}
    
    # Initialize and capture output
    docker exec ${VAULT_CONTAINER} vault operator init \
        -key-shares=${KEY_SHARES} \
        -key-threshold=${KEY_THRESHOLD} \
        -format=json > ${SECRETS_DIR}/vault_keys.json
    
    chmod 600 ${SECRETS_DIR}/vault_keys.json
    
    log_success "Vault initialized"
    
    # Extract and display keys (for backup)
    log_info "Unseal Keys (SAVE THESE SECURELY):"
    echo ""
    jq -r '.unseal_keys_b64[]' ${SECRETS_DIR}/vault_keys.json | nl -w2 -s': '
    echo ""
    
    log_info "Root Token:"
    jq -r '.root_token' ${SECRETS_DIR}/vault_keys.json
    echo ""
}

# Unseal Vault
unseal_vault() {
    log_info "Unsealing Vault..."
    
    if [[ ! -f "${SECRETS_DIR}/vault_keys.json" ]]; then
        log_error "Keys file not found at ${SECRETS_DIR}/vault_keys.json"
        exit 1
    fi
    
    # Get unseal keys
    KEYS=$(jq -r '.unseal_keys_b64[]' ${SECRETS_DIR}/vault_keys.json | head -${KEY_THRESHOLD})
    
    # Unseal with threshold number of keys
    for key in ${KEYS}; do
        docker exec ${VAULT_CONTAINER} vault operator unseal ${key} > /dev/null
    done
    
    # Verify unsealed
    if docker exec ${VAULT_CONTAINER} vault status | grep -q "Sealed.*false"; then
        log_success "Vault unsealed successfully"
    else
        log_error "Failed to unseal Vault"
        exit 1
    fi
}

# Setup secrets engine and policies
setup_secrets() {
    log_info "Setting up secrets engine and policies..."
    
    ROOT_TOKEN=$(jq -r '.root_token' ${SECRETS_DIR}/vault_keys.json)
    
    # Enable KV secrets engine
    docker exec -e VAULT_TOKEN=${ROOT_TOKEN} ${VAULT_CONTAINER} \
        vault secrets enable -path=upgrade kv-v2 2>/dev/null || true
    
    # Create policy for application
    cat > /tmp/upgrade-policy.hcl << 'EOF'
# Policy for UPGRADE application
path "upgrade/data/*" {
  capabilities = ["read", "list"]
}

path "upgrade/metadata/*" {
  capabilities = ["read", "list"]
}
EOF
    
    docker cp /tmp/upgrade-policy.hcl ${VAULT_CONTAINER}:/tmp/upgrade-policy.hcl
    docker exec -e VAULT_TOKEN=${ROOT_TOKEN} ${VAULT_CONTAINER} \
        vault policy write upgrade-app /tmp/upgrade-policy.hcl
    
    rm /tmp/upgrade-policy.hcl
    
    log_success "Secrets engine and policies configured"
}

# Create application token
create_app_token() {
    log_info "Creating application token..."
    
    ROOT_TOKEN=$(jq -r '.root_token' ${SECRETS_DIR}/vault_keys.json)
    
    # Create token with policy
    APP_TOKEN=$(docker exec -e VAULT_TOKEN=${ROOT_TOKEN} ${VAULT_CONTAINER} \
        vault token create \
        -policy=upgrade-app \
        -ttl=720h \
        -renewable=true \
        -format=json | jq -r '.auth.client_token')
    
    # Save app token
    echo ${APP_TOKEN} > ${SECRETS_DIR}/app_token.txt
    chmod 600 ${SECRETS_DIR}/app_token.txt
    
    log_success "Application token created and saved to ${SECRETS_DIR}/app_token.txt"
    echo ""
    log_info "App Token: ${APP_TOKEN}"
    echo ""
    log_warning "Add this to your .env file:"
    echo "VAULT_TOKEN=${APP_TOKEN}"
}

# Print summary
print_summary() {
    echo ""
    echo "============================================================"
    echo -e "${GREEN}Vault Initialization Complete!${NC}"
    echo "============================================================"
    echo ""
    echo "Files created:"
    echo "  - ${SECRETS_DIR}/vault_keys.json (unseal keys + root token)"
    echo "  - ${SECRETS_DIR}/app_token.txt (application token)"
    echo ""
    echo -e "${RED}CRITICAL SECURITY NOTICE:${NC}"
    echo "  1. Backup ${SECRETS_DIR}/vault_keys.json to a secure location"
    echo "  2. Consider using a password manager (1Password, etc.)"
    echo "  3. Delete local copies after backup"
    echo "  4. Never commit these files to Git"
    echo ""
    echo "Next Steps:"
    echo "  1. Run ./store_secrets.sh to populate secrets"
    echo "  2. Update .env with VAULT_TOKEN"
    echo "  3. Restart application services"
    echo ""
}

# Main execution
main() {
    echo ""
    echo "============================================================"
    echo "  UPGRADE Platform - Vault Initialization"
    echo "============================================================"
    echo ""
    
    check_root
    wait_for_vault
    
    if check_initialized; then
        initialize_vault
        unseal_vault
    fi
    
    setup_secrets
    create_app_token
    print_summary
}

main "$@"
