#!/usr/bin/env bash
# Build script for Render deployment
# This script installs Playwright browsers

echo "=== Starting Build Process ==="

echo "Step 1: Installing Python dependencies..."
pip install -r requirements.txt

echo "Step 2: Verifying Playwright installation..."
python -m playwright --version

echo "Step 3: Installing Playwright Chromium browser..."
# Install chromium browser - this is critical
python -m playwright install chromium

echo "Step 4: Installing system dependencies for Playwright..."
# Install system dependencies (required for headless mode on Linux)
# This may fail on some systems but is not always critical
python -m playwright install-deps chromium 2>&1 || echo "Note: install-deps had issues, but continuing..."

echo "Step 5: Verifying browser installation..."
# Verify that browsers were installed correctly
python -c "
from playwright.sync_api import sync_playwright
try:
    p = sync_playwright().start()
    chromium_path = p.chromium.executable_path
    print(f'SUCCESS: Chromium found at: {chromium_path}')
    import os
    if os.path.exists(chromium_path):
        print('SUCCESS: Chromium executable exists!')
    else:
        print(f'ERROR: Chromium executable NOT found at: {chromium_path}')
    p.stop()
except Exception as e:
    print(f'ERROR verifying browser: {e}')
    exit(1)
"

if [ $? -eq 0 ]; then
    echo "=== Build completed successfully! ==="
else
    echo "=== Build completed with warnings - check logs above ==="
    exit 1
fi

