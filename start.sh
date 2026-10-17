#!/usr/bin/env bash
# Helper script to run the WhatsApp bridge from the correct directory

# Get the directory where this script is located
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

if [ ! -f "bridge/wa-bridge" ]; then
    echo "🔨 Bridge binary not found — building it now (needs Go 1.25+)…"
    (cd bridge && go build -o wa-bridge .) || {
        echo "❌ Build failed. Install Go first: https://go.dev/dl/"
        exit 1
    }
fi

if [ ! -d "${STORE_DIR:-store}" ]; then
    echo "⚠️ Warning: '${STORE_DIR:-store}' directory not found. You might need to authenticate."
fi

echo "🚀 Starting Mosaic bridge…"
echo "   Setup page: http://localhost:${PORT:-8081}/  (health: /health)"
echo "   The setup password prints below (or set SETUP_PASSWORD in .env)."
./bridge/wa-bridge
