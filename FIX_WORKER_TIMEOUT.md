# Fix: Worker Timeout During Browser Installation

## The Problem

From your logs, I can see:
1. ✅ Browsers are installing: "INFO: ✅ Playwright browsers installed successfully!"
2. ❌ But it's installing regular chromium, not headless shell
3. ❌ Worker timeout: "WORKER TIMEOUT (pid:57)" - installation takes too long
4. ❌ When launching: Looking for `chromium_headless_shell-1187` but only `chromium-1187` exists

## Root Cause

1. **Wrong browser installed**: Installing all browsers or regular chromium instead of headless shell
2. **Worker timeout**: Installation takes longer than Render's worker timeout (usually 30 seconds)
3. **Verification fails**: Code thinks browsers are installed but headless shell is missing

## ✅ Solution Applied

I've updated the code to:
1. **Install headless shell specifically** (not all browsers - faster)
2. **Verify headless shell works** before marking as installed
3. **Install in background** to avoid worker timeouts

## What Changed

### Before:
- Installed all browsers (slow, causes timeout)
- Didn't verify headless shell
- Checked for regular chromium, not headless shell

### After:
- Installs `chromium-headless-shell` specifically (faster)
- Verifies headless shell actually works
- Checks for headless shell, not regular chromium

## Expected Behavior Now

1. **User visits URL** → Background installation starts
2. **Installation** → Only headless shell (faster, ~2-3 minutes)
3. **Verification** → Tests that headless mode actually works
4. **User submits form** → Headless shell is ready!

## If Still Getting Timeouts

### Option 1: Increase Gunicorn Timeout

In Render, add environment variable:
- Key: `GUNICORN_TIMEOUT`
- Value: `600` (10 minutes)

### Option 2: Install During Build

Update build command to install headless shell:
```bash
pip install -r requirements.txt && python -m playwright install chromium-headless-shell --force
```

This way browsers are ready before app starts.

## Next Steps

1. **Commit and push** the updated code
2. **Redeploy** on Render
3. **Test** - should install headless shell correctly now

The code now installs the correct browser (headless shell) and verifies it works! 🎉

