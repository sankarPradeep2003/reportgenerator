# Troubleshooting Guide

## Chrome Not Opening Locally (Windows/Mac)

### Step 1: Check Playwright Installation

1. **Verify Playwright is installed**:
   ```bash
   pip list | grep playwright
   ```
   Should show: `playwright 1.55.0` (or similar)

2. **If not installed, install it**:
   ```bash
   pip install playwright
   ```

### Step 2: Install Playwright Browsers

1. **Install Chromium browser**:
   ```bash
   python -m playwright install chromium
   ```

2. **Verify installation**:
   ```bash
   python -m playwright install --help
   ```

### Step 3: Check Console Output

When you click "Auto-Login", check the terminal/console where you ran `python app.py`. You should see:
```
DEBUG: Platform: Windows, Headless: False, RENDER: None, HEADLESS: None
DEBUG: Attempting to launch system Chrome...
DEBUG: System Chrome launched successfully!
```

If you see errors, note them down.

### Step 4: Common Issues

**Issue: "Failed to launch browser"**
- **Solution**: Make sure Chrome is installed on your system
- **Alternative**: The app will try to use bundled Chromium as fallback

**Issue: "Playwright not installed"**
- **Solution**: Run `pip install playwright` and `python -m playwright install chromium`

**Issue: Browser launches but closes immediately**
- **Check**: Look for error messages in the console
- **Check**: Make sure all form fields are filled correctly

### Step 5: Test Playwright Directly

Create a test file `test_playwright.py`:
```python
import asyncio
from playwright.async_api import async_playwright

async def test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        await page.goto("https://example.com")
        await asyncio.sleep(5)
        await browser.close()

asyncio.run(test())
```

Run it:
```bash
python test_playwright.py
```

If this doesn't open a browser, Playwright isn't set up correctly.

---

## Reports Not Generating on Render

### Step 1: Check Render Logs

1. Go to your Render dashboard
2. Click on your service
3. Click "Logs" tab
4. Look for error messages

### Step 2: Check Build Logs

1. In Render dashboard, check "Events" or "Build Logs"
2. Verify that Playwright browsers were installed:
   ```
   Installing Playwright browsers...
   Build completed successfully!
   ```

### Step 3: Verify Environment Variables

In Render dashboard → Settings → Environment:
- `HEADLESS` = `true` ✅
- `FLASK_SECRET` = (generated) ✅
- `FLASK_ENV` = `production` ✅

### Step 4: Check Runtime Logs

Look for these messages in Render logs:
```
DEBUG: Platform: Linux, Headless: True, RENDER: true, HEADLESS: true
DEBUG: Launching headless browser...
DEBUG: Headless browser launched successfully!
```

### Step 5: Common Render Issues

**Issue: "Failed to launch headless browser"**
- **Cause**: Playwright browsers not installed during build
- **Solution**: Check build logs, ensure `build.sh` ran successfully
- **Fix**: Redeploy and watch build logs

**Issue: "No open ports detected"**
- **Cause**: App not binding to correct port
- **Solution**: Already fixed in code (uses `PORT` env var)

**Issue: Reports generate but files not downloadable**
- **Check**: `server_downloads/` directory exists
- **Check**: Files are being saved correctly
- **Check**: Download endpoint is working (`/download/<file_id>`)

**Issue: Timeout errors**
- **Cause**: Report generation takes longer than expected
- **Solution**: Increase timeout in code or check network connectivity

### Step 6: Test Headless Mode Locally

To test if headless mode works (simulating Render):

1. **Set environment variable**:
   ```bash
   # Windows PowerShell
   $env:HEADLESS="true"
   python app.py
   
   # Windows CMD
   set HEADLESS=true
   python app.py
   
   # Mac/Linux
   export HEADLESS=true
   python app.py
   ```

2. **Try auto-login** - it should work without opening a visible browser

### Step 7: Check API Endpoints

Test these endpoints on Render:

1. **Health check**: `https://your-app.onrender.com/`
2. **Downloads list**: `https://your-app.onrender.com/api/downloads`
3. **Generation status**: `https://your-app.onrender.com/api/generation-status`

---

## Debugging Tips

### Enable More Debug Output

The code now includes debug print statements. Check:
- **Local**: Terminal where you run `python app.py`
- **Render**: Logs tab in Render dashboard

### Check Process Status

After clicking "Auto-Login", you can check status:
- Visit: `http://localhost:8000/api/generation-status` (local)
- Visit: `https://your-app.onrender.com/api/generation-status` (Render)

### Common Error Messages

| Error | Cause | Solution |
|-------|-------|----------|
| "Playwright not installed" | Missing package | `pip install playwright` |
| "Failed to launch browser" | Browsers not installed | `python -m playwright install chromium` |
| "Failed to launch headless browser" | Build issue on Render | Check build logs, redeploy |
| "No open ports detected" | Port binding issue | Already fixed in code |
| "Report generation was cancelled" | User cancelled | Normal behavior |

---

## Still Having Issues?

1. **Check all logs** (local terminal + Render logs)
2. **Verify all dependencies** are installed
3. **Test Playwright directly** (see Step 5 above)
4. **Check Render build logs** for Playwright installation
5. **Try a fresh deployment** on Render

If issues persist, share:
- Error messages from logs
- Platform (Windows/Mac/Linux)
- Whether it's local or Render
- Steps you've already tried

