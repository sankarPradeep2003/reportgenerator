# Quick Fix: Playwright Browsers Not Installing on Render

## Immediate Solution

### Option 1: Update Build Command in Render (Recommended)

1. Go to **Render Dashboard** → Your Service → **Settings**
2. Find **"Build Command"** field
3. Replace it with this exact command:
   ```bash
   pip install -r requirements.txt && python -m playwright install chromium && python -m playwright install-deps chromium
   ```
4. **Save** and **Redeploy**

### Option 2: Use the Updated build.sh (Already Updated)

The `build.sh` file has been updated. Just:
1. **Commit and push**:
   ```bash
   git add build.sh
   git commit -m "Fix Playwright browser installation"
   git push origin main
   ```
2. **Redeploy** on Render (should auto-deploy)

### Option 3: Clear Cache and Rebuild

1. Go to **Render Dashboard** → Your Service
2. Click **"Manual Deploy"**
3. Select **"Clear build cache & deploy"**
4. This forces a completely fresh build

---

## What to Check in Build Logs

After redeploying, check the build logs for:

### ✅ Success Indicators:
```
Step 3: Installing Playwright Chromium browser...
SUCCESS: Chromium found at: /opt/render/.cache/ms-playwright/chromium-XXXX/chrome-linux/chrome
SUCCESS: Chromium executable exists!
=== Build completed successfully! ===
```

### ❌ Failure Indicators:
```
ERROR: Chromium executable NOT found
ERROR verifying browser: [error message]
```

---

## If Still Not Working

### Try This Alternative Build Command:

```bash
pip install --upgrade pip && pip install -r requirements.txt && python -m playwright install --with-deps chromium
```

The `--with-deps` flag installs both the browser and system dependencies in one command.

---

## Verify After Deployment

1. **Check Runtime Logs** (not build logs)
2. Submit a report generation request
3. Look for:
   ```
   DEBUG: Launching headless browser...
   DEBUG: Headless browser launched successfully!
   ```

If you still see the error about executable not existing, the browsers didn't install correctly during build.

---

## Root Cause

The error happens because:
1. Playwright Python package is installed ✅
2. But the actual Chromium browser binary is NOT downloaded ❌

The `playwright install chromium` command must run during the build phase to download the browser binaries.

---

## Next Steps

1. **Try Option 1 first** (update build command directly in Render)
2. **Watch the build logs** to see if browsers install
3. **Test the app** after deployment
4. If it still fails, check the build logs and share the error messages

