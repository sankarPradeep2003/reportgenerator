# Fix Playwright Browser Installation on Render

## The Problem
Playwright browsers are not being installed during the build process, causing the error:
```
Executable doesn't exist at /opt/render/.cache/ms-playwright/chromium_headless_shell-1187/chrome-linux/headless_shell
```

## Solution: Update Build Command in Render

### Step 1: Go to Render Dashboard
1. Go to https://dashboard.render.com
2. Click on your service (reportgenerator)

### Step 2: Update Build Command
1. Click on **"Settings"** tab
2. Scroll down to **"Build Command"**
3. **Replace** the current build command with this EXACT command:

```bash
pip install -r requirements.txt && python -m playwright install chromium && python -m playwright install-deps chromium
```

**OR** use this alternative (more robust):

```bash
pip install -r requirements.txt && python -m playwright install --with-deps chromium
```

### Step 3: Clear Build Cache and Redeploy
1. Go to **"Events"** tab
2. Click **"Manual Deploy"** dropdown
3. Select **"Clear build cache & deploy"**
4. Wait for the build to complete (5-10 minutes)

### Step 4: Verify Installation
After deployment, check the build logs. You should see:
- "Installing Playwright browsers..."
- "Installing Playwright system dependencies..."
- No errors about missing executables

## Alternative: Use Build Script

If the direct command doesn't work, use the build script:

1. In Render Settings, set **Build Command** to:
```bash
chmod +x build.sh && ./build.sh
```

2. Make sure `build.sh` is in your repository root (in the `reportgenerator` folder)

## What Changed in the Code

1. **Added startup check**: The app now checks if browsers are installed when it starts
2. **Improved error handling**: Better error messages to diagnose issues
3. **Updated build script**: More robust browser installation

## Troubleshooting

### If browsers still don't install:

1. **Check build logs** for errors during installation
2. **Try installing all browsers** instead of just chromium:
   ```bash
   pip install -r requirements.txt && python -m playwright install --with-deps
   ```
3. **Check Python version**: Make sure you're using Python 3.11 (check `runtime.txt`)
4. **Verify requirements.txt**: Ensure `playwright==1.55.0` is listed

### If you see "Permission denied" errors:

Add this to your build command:
```bash
pip install -r requirements.txt && python -m playwright install chromium && python -m playwright install-deps chromium || python -m playwright install --with-deps chromium
```

## Expected Build Log Output

You should see something like:
```
Installing Python dependencies...
Installing Playwright browsers...
Downloading chromium...
Installing Playwright system dependencies...
Chromium found at: /opt/render/.cache/ms-playwright/chromium-XXXX/chrome-linux/chrome
Path exists: True
Build completed successfully!
```

## After Fixing

Once the build succeeds:
1. The app will start successfully
2. Check the logs tab - you should see: "Playwright browsers found at: ..."
3. Try submitting the form - it should work now!

