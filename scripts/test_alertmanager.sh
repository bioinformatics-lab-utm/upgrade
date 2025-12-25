#!/bin/bash
# Test Alertmanager Configuration
# This script sends a test alert to verify alerting is working

set -e

echo "🧪 Testing Alertmanager Configuration..."
echo ""

# Check if alertmanager is running
if ! docker ps | grep -q "alertmanager"; then
    echo "❌ ERROR: Alertmanager container is not running"
    echo "   Start it with: docker compose up -d alertmanager"
    exit 1
fi

echo "✅ Alertmanager is running"
echo ""

# Test 1: Check Alertmanager API is accessible
echo "📡 Test 1: Checking Alertmanager API..."
if curl -s -f http://localhost:9093/-/healthy > /dev/null; then
    echo "✅ Alertmanager API is healthy"
else
    echo "❌ Alertmanager API is not accessible"
    exit 1
fi
echo ""

# Test 2: Send a test alert
echo "📧 Test 2: Sending test alert..."
ALERT_PAYLOAD=$(cat <<EOF
[
  {
    "labels": {
      "alertname": "TestAlert",
      "severity": "info",
      "instance": "test-instance",
      "job": "test",
      "category": "testing"
    },
    "annotations": {
      "summary": "This is a test alert",
      "description": "If you receive this email, alerting is configured correctly! This alert was sent from the test_alertmanager.sh script."
    },
    "startsAt": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "endsAt": "$(date -u -d '+5 minutes' +%Y-%m-%dT%H:%M:%SZ)"
  }
]
EOF
)

RESPONSE=$(curl -s -w "\n%{http_code}" -X POST http://localhost:9093/api/v1/alerts \
  -H "Content-Type: application/json" \
  -d "$ALERT_PAYLOAD")

HTTP_CODE=$(echo "$RESPONSE" | tail -n 1)
BODY=$(echo "$RESPONSE" | head -n -1)

if [ "$HTTP_CODE" = "200" ]; then
    echo "✅ Test alert sent successfully"
    echo "   Response: $BODY"
else
    echo "❌ Failed to send test alert"
    echo "   HTTP Code: $HTTP_CODE"
    echo "   Response: $BODY"
    exit 1
fi
echo ""

# Test 3: Check alert appears in Alertmanager UI
echo "🔍 Test 3: Verifying alert in Alertmanager..."
sleep 2
ALERTS=$(curl -s http://localhost:9093/api/v1/alerts)

if echo "$ALERTS" | grep -q "TestAlert"; then
    echo "✅ Alert visible in Alertmanager UI"
    echo "   View at: http://localhost:9093/#/alerts"
else
    echo "⚠️  Alert not yet visible (may take a few seconds)"
fi
echo ""

# Test 4: Check Prometheus connection to Alertmanager
echo "🔗 Test 4: Checking Prometheus → Alertmanager connection..."
if docker exec upgrade_prometheus wget -q -O - http://alertmanager:9093/-/healthy > /dev/null 2>&1; then
    echo "✅ Prometheus can reach Alertmanager"
else
    echo "❌ Prometheus cannot reach Alertmanager"
    echo "   Check docker network configuration"
fi
echo ""

# Test 5: Check if alert rules are loaded
echo "📋 Test 5: Checking alert rules in Prometheus..."
RULES=$(curl -s http://localhost:9090/api/v1/rules)

if echo "$RULES" | grep -q "ServiceDown"; then
    echo "✅ Alert rules loaded successfully"
    RULE_COUNT=$(echo "$RULES" | grep -o '"alertname"' | wc -l)
    echo "   Found $RULE_COUNT alert rules"
else
    echo "❌ Alert rules not loaded"
    echo "   Check prometheus.yml and alert_rules.yml"
fi
echo ""

# Summary
echo "═══════════════════════════════════════════"
echo "📊 TEST SUMMARY"
echo "═══════════════════════════════════════════"
echo ""
echo "Alertmanager URL:  http://localhost:9093"
echo "Prometheus URL:    http://localhost:9090"
echo "Grafana URL:       http://localhost:3001"
echo ""
echo "⏰ Test alert will resolve automatically in 5 minutes"
echo ""
echo "📧 Check your email (${ALERT_EMAIL_TO:-configured address}) for test alert notification"
echo ""
echo "💡 Tips:"
echo "   • View active alerts: http://localhost:9093/#/alerts"
echo "   • View alert rules: http://localhost:9090/alerts"
echo "   • Check alertmanager logs: docker logs upgrade_alertmanager"
echo "   • Check prometheus logs: docker logs upgrade_prometheus"
echo ""

# Check email configuration
echo "📝 Email Configuration Check:"
SMTP_HOST_CHECK=$(grep "SMTP_HOST=" .env | cut -d'=' -f2)
ALERT_EMAIL_CHECK=$(grep "ALERT_EMAIL_TO=" .env | cut -d'=' -f2)

if [ "$SMTP_HOST_CHECK" = "smtp.sendgrid.net" ] && [ "$ALERT_EMAIL_CHECK" = "your-email@example.com" ]; then
    echo "⚠️  WARNING: Email configuration not updated!"
    echo ""
    echo "   To receive email alerts, update .env file:"
    echo "   1. SMTP_HOST=smtp.gmail.com (for Gmail)"
    echo "   2. SMTP_PORT=587"
    echo "   3. SMTP_USER=your-email@gmail.com"
    echo "   4. SMTP_PASSWORD=<your-app-password>"
    echo "   5. SMTP_FROM_EMAIL=your-email@gmail.com"
    echo "   6. ALERT_EMAIL_TO=your-email@gmail.com"
    echo ""
    echo "   For Gmail App Password:"
    echo "   → https://myaccount.google.com/apppasswords"
    echo ""
else
    echo "✅ Email configuration appears set"
    echo "   Sending to: $ALERT_EMAIL_CHECK"
fi

echo ""
echo "✅ All tests completed!"
