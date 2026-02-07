#!/usr/bin/env bash
# Quick update script for demo agent on Railway production
# Usage: ./update-demo-agent.sh

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "🚀 Updating Alyx demo agent on Railway production..."
echo ""

cd "$PROJECT_DIR"

# Check if a service is linked
if ! railway status 2>&1 | grep -q "Service:"; then
    echo "⚠️  No Railway service linked. Linking now..."
    echo ""
    echo "Available services:"
    railway service list 2>/dev/null || echo "  Run 'railway service' to link a service"
    echo ""
    echo "💡 Tip: Run 'railway service' and select your backend service"
    exit 1
fi

# Run the create_demo_agent script on Railway
railway run python scripts/create_demo_agent.py

echo ""
echo "✅ Demo agent updated successfully!"
echo ""
echo "To view logs:    railway logs"
echo "To open Railway: railway open"
