#!/bin/bash
set -e

echo "Installing Python dependencies..."
pip install -r requirements.txt

echo "Installing Playwright browsers..."
python -m playwright install chromium

echo "Installing Playwright system dependencies..."
python -m playwright install-deps chromium

echo "Build completed successfully!"

