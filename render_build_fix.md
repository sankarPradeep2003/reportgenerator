# Fix for Playwright Browser Installation on Render

## The Problem
Playwright browsers are not being installed during the build process, causing the error:
```
Executable doesn't exist at /opt/render/.cache/ms-playwright/chromium_headless_shell-1187/chrome-linux/headless_shell
```

## Solution 1: Updated Build Script (Already Applied)

The `build.sh` script has been updated with better error handling and verification.

## Solution 2: Manual Build Command Override

If the build script still doesn't work, you can override it in Render:

### Steps:
1. Go to Render Dashboard → Your Service → Settings
2. Find "Build Command"
3. Replace with:
   ```bash
   pip install -r requirements.txt && python -m playwright install chromium && python -m playwright install-deps chromium
   ```

## Solution 3: Add to requirements.txt (Alternative)

Some users have success by ensuring Playwright is installed correctly. The current `requirements.txt` should have:
```
Flask==3.0.3
playwright==1.55.0
gunicorn==21.2.0
```

## Solution 4: Check Build Logs

1. Go to Render Dashboard → Your Service
2. Click "Events" or check build logs
3. Look for these messages:
   ```
   Installing Playwright browsers...
   playwright install chromium
   ```
4. If you see errors, note them down

## Solution 5: Force Rebuild

1. Go to Render Dashboard → Your Service
2. Click "Manual Deploy"
3. Select "Clear build cache & deploy"
4. This forces a fresh build

## Verification

After deployment, check the build logs for:
```
Installing Playwright browsers...
Checking installed browsers...
Build completed successfully!
```

If you see errors during browser installation, the build logs will show them.

## Common Issues

### Issue: "playwright: command not found"
- **Cause**: Playwright not installed
- **Fix**: Ensure `pip install -r requirements.txt` runs before `playwright install`

### Issue: "Permission denied"
- **Cause**: Build script not executable
- **Fix**: The build command includes `chmod +x build.sh` which should fix this

### Issue: Browsers install but can't find them
- **Cause**: Path issues or cache problems
- **Fix**: Use "Clear build cache & deploy" option

## Next Steps

1. **Commit the updated build.sh**:
   ```bash
   git add build.sh
   git commit -m "Fix Playwright browser installation"
   git push origin main
   ```

2. **Redeploy on Render**:
   - Go to your service
   - Click "Manual Deploy" → "Clear build cache & deploy"

3. **Watch the build logs** to see if browsers install correctly

4. **Test the application** after deployment

