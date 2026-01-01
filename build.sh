#!/usr/bin/env bash
# Build script for Render deployment
# This script installs Playwright browsers

echo "Installing Python dependencies..."
pip install -r requirements.txt

echo "Installing Playwright browsers..."
python -m playwright install chromium
python -m playwright install-deps chromium

echo "Build completed successfully!"

