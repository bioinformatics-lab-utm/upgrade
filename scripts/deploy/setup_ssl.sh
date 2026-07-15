#!/bin/bash
# =============================================================================
# UPGRADE Platform - SSL/TLS Setup with Let's Encrypt
# =============================================================================
# This script sets up SSL certificates for upgrade.utm.md
# Usage: sudo ./setup_ssl.sh
# =============================================================================

set -euo pipefail

# Configuration
DOMAIN="upgrade.utm.md"
EMAIL="viorel.munteanu@utm.md"
CERTBOT_DIR="/etc/letsencrypt"
WEBROOT_DIR="/var/www/certbot"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root (use sudo)"
        exit 1
    fi
}

# Install dependencies
install_dependencies() {
    log_info "Installing Certbot and dependencies..."
    
    apt-get update
    apt-get install -y certbot python3-certbot-nginx
    
    log_success "Dependencies installed"
}

# Create webroot directory
setup_webroot() {
    log_info "Setting up webroot directory..."
    
    mkdir -p ${WEBROOT_DIR}
    chown -R www-data:www-data ${WEBROOT_DIR}
    chmod 755 ${WEBROOT_DIR}
    
    log_success "Webroot directory created at ${WEBROOT_DIR}"
}

# Check if certificate already exists
check_existing_cert() {
    if [[ -d "${CERTBOT_DIR}/live/${DOMAIN}" ]]; then
        log_warning "Certificate already exists for ${DOMAIN}"
        read -p "Do you want to renew/replace it? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "Keeping existing certificate"
            return 1
        fi
    fi
    return 0
}

# Stop services that might use port 80
stop_conflicting_services() {
    log_info "Stopping services that might conflict with Certbot..."
    
    # Stop nginx if running
    systemctl stop nginx 2>/dev/null || true
    
    # Stop Apache if running
    systemctl stop apache2 2>/dev/null || true
    
    # Stop Docker nginx container if running
    docker stop upgrade_nginx 2>/dev/null || true
    
    log_success "Conflicting services stopped"
}

# Generate SSL certificate
generate_certificate() {
    log_info "Generating SSL certificate for ${DOMAIN}..."
    
    certbot certonly --standalone \
        --non-interactive \
        --agree-tos \
        --email ${EMAIL} \
        --domains ${DOMAIN},www.${DOMAIN} \
        --preferred-challenges http
    
    log_success "SSL certificate generated"
}

# Verify certificate
verify_certificate() {
    log_info "Verifying SSL certificate..."
    
    if [[ -f "${CERTBOT_DIR}/live/${DOMAIN}/fullchain.pem" ]]; then
        openssl x509 -in "${CERTBOT_DIR}/live/${DOMAIN}/fullchain.pem" -noout -text | head -20
        
        # Check expiration date
        EXPIRY=$(openssl x509 -in "${CERTBOT_DIR}/live/${DOMAIN}/fullchain.pem" -noout -enddate | cut -d= -f2)
        log_success "Certificate valid until: ${EXPIRY}"
    else
        log_error "Certificate files not found!"
        exit 1
    fi
}

# Setup automatic renewal
setup_renewal() {
    log_info "Setting up automatic certificate renewal..."
    
    # Create renewal hook script
    mkdir -p /etc/letsencrypt/renewal-hooks/deploy
    cat > /etc/letsencrypt/renewal-hooks/deploy/upgrade-reload.sh << 'EOF'
#!/bin/bash
# Reload nginx after certificate renewal
docker exec upgrade_nginx nginx -s reload 2>/dev/null || systemctl reload nginx 2>/dev/null || true
echo "$(date): Certificate renewed and services reloaded" >> /var/log/certbot-renewal.log
EOF
    chmod +x /etc/letsencrypt/renewal-hooks/deploy/upgrade-reload.sh
    
    # Add cron job for renewal (twice daily as recommended by Let's Encrypt)
    cat > /etc/cron.d/certbot-renewal << EOF
# Certbot automatic certificate renewal
0 0,12 * * * root certbot renew --quiet --deploy-hook "/etc/letsencrypt/renewal-hooks/deploy/upgrade-reload.sh"
EOF
    
    # Enable and start the certbot timer (systemd-based renewal)
    systemctl enable certbot.timer 2>/dev/null || true
    systemctl start certbot.timer 2>/dev/null || true
    
    log_success "Automatic renewal configured"
}

# Create certificate bundle for nginx
create_nginx_bundle() {
    log_info "Creating nginx certificate bundle..."
    
    mkdir -p /etc/nginx/ssl
    
    # Create combined certificate for nginx
    cat "${CERTBOT_DIR}/live/${DOMAIN}/fullchain.pem" > /etc/nginx/ssl/upgrade.crt
    cat "${CERTBOT_DIR}/live/${DOMAIN}/privkey.pem" > /etc/nginx/ssl/upgrade.key
    
    # Generate DH parameters for perfect forward secrecy
    if [[ ! -f /etc/nginx/ssl/dhparam.pem ]]; then
        log_info "Generating DH parameters (this may take a few minutes)..."
        openssl dhparam -out /etc/nginx/ssl/dhparam.pem 2048
    fi
    
    # Set proper permissions
    chmod 600 /etc/nginx/ssl/*
    
    log_success "Nginx certificate bundle created"
}

# Test certificate
test_certificate() {
    log_info "Testing SSL certificate..."
    
    # Test with openssl
    if openssl s_client -connect ${DOMAIN}:443 -servername ${DOMAIN} </dev/null 2>/dev/null | openssl x509 -noout -dates; then
        log_success "SSL certificate is working"
    else
        log_warning "Could not verify certificate (server might not be running yet)"
    fi
}

# Print summary
print_summary() {
    echo ""
    echo "============================================================"
    echo -e "${GREEN}SSL/TLS Setup Complete!${NC}"
    echo "============================================================"
    echo ""
    echo "Certificate Location:"
    echo "  - Full Chain: ${CERTBOT_DIR}/live/${DOMAIN}/fullchain.pem"
    echo "  - Private Key: ${CERTBOT_DIR}/live/${DOMAIN}/privkey.pem"
    echo "  - Certificate: ${CERTBOT_DIR}/live/${DOMAIN}/cert.pem"
    echo "  - Chain: ${CERTBOT_DIR}/live/${DOMAIN}/chain.pem"
    echo ""
    echo "Nginx Bundle:"
    echo "  - Certificate: /etc/nginx/ssl/upgrade.crt"
    echo "  - Private Key: /etc/nginx/ssl/upgrade.key"
    echo "  - DH Params: /etc/nginx/ssl/dhparam.pem"
    echo ""
    echo "Next Steps:"
    echo "  1. Update docker-compose.prod.yml to mount certificates"
    echo "  2. Start nginx: docker-compose -f docker-compose.prod.yml up -d nginx"
    echo "  3. Test: curl -I https://${DOMAIN}"
    echo "  4. SSL Labs: https://www.ssllabs.com/ssltest/analyze.html?d=${DOMAIN}"
    echo ""
    echo "Automatic Renewal:"
    echo "  - Cron job configured to run twice daily"
    echo "  - Logs: /var/log/certbot-renewal.log"
    echo ""
}

# Main execution
main() {
    echo ""
    echo "============================================================"
    echo "  UPGRADE Platform - SSL/TLS Setup"
    echo "  Domain: ${DOMAIN}"
    echo "============================================================"
    echo ""
    
    check_root
    
    if check_existing_cert; then
        install_dependencies
        setup_webroot
        stop_conflicting_services
        generate_certificate
    fi
    
    verify_certificate
    create_nginx_bundle
    setup_renewal
    test_certificate
    print_summary
}

# Run main function
main "$@"
