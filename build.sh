#!/bin/bash
set -e

echo "Installing Python dependencies..."
pip install -r requirements.txt

echo "Installing Playwright browsers..."
python -m playwright install chromium

echo "Installing Playwright system dependencies..."
python -m playwright install-deps chromium

echo "Verifying Playwright installation..."
python -c "from playwright.sync_api import sync_playwright; p = sync_playwright().start(); browser_path = p.chromium.executable_path; print(f'Chromium found at: {browser_path}'); import os; print(f'Path exists: {os.path.exists(browser_path)}'); p.stop()"

echo "Build completed successfully!"

