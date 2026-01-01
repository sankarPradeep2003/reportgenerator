# Build Command Options for Render

## Option 1: Robust Build Command (Recommended)

Use this in Render's Build Command field:

```bash
pip install -r requirements.txt && python -m playwright install chromium || (echo "Playwright install failed, retrying..." && python -m playwright install chromium) && echo "Build successful"
```

## Option 2: Simple Build Command (Most Reliable)

```bash
pip install -r requirements.txt && python -m playwright install chromium
```

**Note:** This skips `install-deps` which often fails on Render but isn't always necessary.

## Option 3: With Error Handling

```bash
pip install -r requirements.txt && (python -m playwright install chromium || exit 1) && (python -m playwright install-deps chromium || echo "install-deps skipped") && echo "Build completed"
```

## Option 4: Use the build.sh Script (Current)

If using `render.yaml` or setting build command to use the script:

```bash
chmod +x build.sh && ./build.sh
```

But make sure the script doesn't exit on `install-deps` failures.

---

## Recommended: Option 2 (Simple)

**Why?** 
- `install-deps` often fails on Render but isn't critical
- Chromium works without it in most cases
- Simpler = fewer failure points

## If Build Still Fails

### Check Build Logs For:
1. **"pip install" errors** - Dependencies issue
2. **"playwright install" errors** - Network/timeout issue
3. **Timeout errors** - Build taking too long

### Solutions:
- **Timeout**: Increase build timeout in Render settings
- **Network**: Retry the build (sometimes network issues)
- **Dependencies**: Check `requirements.txt` is correct

