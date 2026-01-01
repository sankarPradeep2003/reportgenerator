# Fix: Worker Timeout During Browser Installation

## The Problem

From your logs:
```
[CRITICAL] WORKER TIMEOUT (pid:57)
Worker (pid:57) was sent SIGKILL! Perhaps out of memory
```

**Root Cause:** Browser installation is happening synchronously during a request, taking longer than Render's worker timeout (30 seconds).

## ✅ Solution: Install During Build

The best solution is to **install browsers during the build phase**, so they're ready when the app starts.

### Update Build Command in Render

1. Go to **Render Dashboard** → Your Service → **Settings**
2. Find **"Build Command"**
3. Replace with:
   ```bash
   pip install -r requirements.txt && python -m playwright install chromium-headless-shell --force
   ```

This installs browsers **during build** (before app starts), so:
- ✅ No worker timeout (build has longer timeout)
- ✅ Browsers ready immediately when app starts
- ✅ No waiting for users

## What I've Fixed in Code

1. **Removed synchronous installation** - Won't try to install during form submission
2. **Background installation only** - Happens in background thread
3. **Better timeout handling** - Won't wait too long (avoids worker timeout)
4. **Updated build script** - Tries Chrome, falls back to Chromium

## Expected Behavior After Fix

### With Build-Time Installation:
1. **Build phase**: Browsers install (takes 2-5 minutes, but build has longer timeout)
2. **App starts**: Browsers already installed ✅
3. **User visits**: Everything works immediately ✅

### Without Build-Time Installation:
1. **User visits**: Background installation starts
2. **User submits form**: If browsers not ready, shows message to wait
3. **After 2-5 minutes**: Browsers ready, user can retry

## Recommended: Use Build-Time Installation

**Build Command:**
```bash
pip install -r requirements.txt && python -m playwright install chromium-headless-shell --force
```

This is the **most reliable** solution - browsers are ready when app starts!

## Alternative: Increase Worker Timeout

If you want to keep runtime installation, add this environment variable in Render:

- **Key**: `GUNICORN_TIMEOUT`
- **Value**: `600` (10 minutes)

But build-time installation is still better!

