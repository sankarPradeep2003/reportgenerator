# Fix: Deployment Failed After Changing Build Command

## Quick Fix - Use This Build Command

In Render Dashboard → Your Service → Settings → Build Command, use:

```bash
pip install -r requirements.txt && python -m playwright install chromium
```

**Why this works:**
- Simple and reliable
- Skips `install-deps` which often fails on Render
- Chromium works without system deps in most cases

---

## Why Your Build Command Failed

The command you used:
```bash
pip install -r requirements.txt && python -m playwright install chromium && python -m playwright install-deps chromium
```

Likely failed because:
1. **`install-deps` fails on Render** - It tries to install system packages which may not be allowed
2. **The `&&` operator** - If any command fails, the whole build fails
3. **Timeout** - Installing deps can take too long

---

## Solution Options

### Option 1: Simple Command (Recommended) ✅

**Build Command:**
```bash
pip install -r requirements.txt && python -m playwright install chromium
```

**Pros:**
- Most reliable
- Fast
- Works on Render

**Cons:**
- Skips system dependencies (usually not needed)

---

### Option 2: With Error Handling

**Build Command:**
```bash
pip install -r requirements.txt && python -m playwright install chromium && (python -m playwright install-deps chromium || true)
```

**Pros:**
- Tries to install deps but doesn't fail if it can't

**Cons:**
- Slightly more complex

---

### Option 3: Use Updated build.sh

**Build Command:**
```bash
chmod +x build.sh && ./build.sh
```

The `build.sh` has been updated to not fail on `install-deps` errors.

---

## Step-by-Step Fix

1. **Go to Render Dashboard**
   - Click on your service
   - Go to "Settings"

2. **Update Build Command**
   - Find "Build Command" field
   - Replace with: `pip install -r requirements.txt && python -m playwright install chromium`
   - **Save**

3. **Redeploy**
   - Click "Manual Deploy"
   - Or wait for auto-deploy if you pushed to git

4. **Check Build Logs**
   - Watch for: "Installing Playwright Chromium browser..."
   - Should see success messages

---

## Verify It Works

After deployment, check runtime logs when you submit a report:

**Success:**
```
DEBUG: Launching headless browser...
DEBUG: Headless browser launched successfully!
```

**Failure:**
```
ERROR: Failed to launch headless browser: Executable doesn't exist
```

---

## If Still Failing

### Check Build Logs For:

1. **"Command not found" errors**
   - Python/pip not in PATH
   - Solution: Use full paths or check Python version

2. **"Permission denied" errors**
   - Can't write to directories
   - Solution: Usually not an issue on Render

3. **"Timeout" errors**
   - Build taking too long
   - Solution: Increase timeout in Render settings

4. **"Network" errors**
   - Can't download browsers
   - Solution: Retry the build

### Share the Error

If it still fails, share:
- The exact error from build logs
- Which step failed (pip install, playwright install, etc.)
- Any timeout messages

---

## Recommended Action

**Use this exact command:**
```bash
pip install -r requirements.txt && python -m playwright install chromium
```

This is the simplest and most reliable option for Render.

