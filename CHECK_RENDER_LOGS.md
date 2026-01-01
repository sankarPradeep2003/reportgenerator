# How to Check Render Logs - Step by Step

## Accessing Render Logs

### Step 1: Go to Render Dashboard
1. Log in to https://render.com
2. Click on your service name (e.g., "reportgenerator")

### Step 2: Open Logs Tab
1. Click on the **"Logs"** tab at the top
2. You'll see real-time logs from your application

### Step 3: What to Look For

When you click "Auto-Login" on your Render app, you should see these messages in the logs:

#### ✅ **Successful Browser Launch:**
```
DEBUG: Platform: Linux, Headless: True, RENDER: true, HEADLESS: true
DEBUG: Launching headless browser...
DEBUG: Headless browser launched successfully!
```

#### ✅ **Successful Login:**
```
Navigating to URL...
Waiting for page load...
Filling login fields...
```

#### ✅ **Successful Report Generation:**
```
Successfully processed [course_name] - [test_name]
File downloaded: [filename].xlsx
```

#### ❌ **If There Are Errors:**
```
ERROR: Failed to launch headless browser: [error message]
ERROR: Report generation failed: [error message]
```

---

## Real-Time Monitoring

### Option 1: Watch Logs in Real-Time
1. Keep the **Logs** tab open
2. Submit a report generation request from your app
3. Watch the logs update in real-time as the process runs

### Option 2: Check Generation Status
Visit this URL in your browser (replace with your app URL):
```
https://your-app-name.onrender.com/api/generation-status
```

This will show:
```json
{
  "active": true,
  "process_id": "...",
  "started_at": 1234567890,
  "cancelled": false,
  "success": true,
  "message": "Report generated successfully"
}
```

### Option 3: Check Available Downloads
Visit:
```
https://your-app-name.onrender.com/api/downloads
```

This shows all generated files ready for download.

---

## Understanding the Log Messages

### Build Phase (During Deployment)
Look for:
```
Installing Python dependencies...
Installing Playwright browsers...
Build completed successfully!
```

### Runtime Phase (When App is Running)

**When you click "Auto-Login":**
1. **Browser Launch:**
   ```
   DEBUG: Platform: Linux, Headless: True, RENDER: true, HEADLESS: true
   DEBUG: Launching headless browser...
   DEBUG: Headless browser launched successfully!
   ```

2. **Navigation:**
   ```
   Navigating to: https://your-url.com
   Page loaded successfully
   ```

3. **Login Process:**
   ```
   Waiting for email field...
   Filling email field...
   Filling password field...
   Clicking login button...
   ```

4. **Report Generation:**
   ```
   Navigating to Courses...
   Searching for course: [course_name]
   Clicking course...
   Selecting module: [module_name]
   Clicking test: [test_name]
   Downloading report...
   File saved: [filename].xlsx
   ```

5. **Completion:**
   ```
   Successfully processed [course_name] - [test_name]
   Report generation completed
   ```

---

## Common Log Patterns

### ✅ Everything Working:
```
DEBUG: Platform: Linux, Headless: True
DEBUG: Headless browser launched successfully!
[Login process logs...]
Successfully processed [course] - [test]
File downloaded: report.xlsx
```

### ❌ Browser Launch Failed:
```
ERROR: Failed to launch headless browser: [error]
```
**Solution:** Check build logs to ensure Playwright browsers were installed

### ❌ Login Failed:
```
ERROR: Failed to fill login fields: [error]
```
**Solution:** Check if URL, username, password are correct

### ❌ Report Generation Failed:
```
ERROR: Report generation failed: [error]
```
**Solution:** Check if course/module/test names are correct

---

## Tips for Monitoring

1. **Keep Logs Tab Open**: While testing, keep the logs tab open to see real-time updates

2. **Scroll to Bottom**: New logs appear at the bottom - scroll down to see latest

3. **Use Search**: Use Ctrl+F (Cmd+F on Mac) to search for specific terms like "ERROR" or "DEBUG"

4. **Check Timestamps**: Logs show timestamps - note when you submitted the request to find relevant logs

5. **Filter by Level**: Look for "ERROR" messages first if something isn't working

---

## Quick Status Check Commands

### From Browser:
- **Health Check**: `https://your-app.onrender.com/`
- **Status API**: `https://your-app.onrender.com/api/generation-status`
- **Downloads API**: `https://your-app.onrender.com/api/downloads`

### From Terminal (using curl):
```bash
# Check if app is running
curl https://your-app.onrender.com/

# Check generation status
curl https://your-app.onrender.com/api/generation-status

# Check available downloads
curl https://your-app.onrender.com/api/downloads
```

---

## Troubleshooting with Logs

### Issue: No logs appearing
- **Check**: Is the service running? Look for "Deployed" status
- **Check**: Are you on the correct service's logs tab?

### Issue: Logs show errors but unclear
- **Look for**: Lines starting with "ERROR:"
- **Check**: The line immediately after the error (often has more details)
- **Share**: The full error message for debugging

### Issue: Process seems stuck
- **Check**: Look for "DEBUG: Headless browser launched successfully!"
- **If missing**: Browser launch failed
- **If present**: Process might be waiting for page elements (check timeout messages)

---

## Example: Complete Successful Flow in Logs

```
[2024-01-15 10:30:15] INFO: Starting report generation
[2024-01-15 10:30:15] DEBUG: Platform: Linux, Headless: True, RENDER: true, HEADLESS: true
[2024-01-15 10:30:16] DEBUG: Launching headless browser...
[2024-01-15 10:30:18] DEBUG: Headless browser launched successfully!
[2024-01-15 10:30:18] INFO: Navigating to: https://example.com
[2024-01-15 10:30:20] INFO: Page loaded, filling login form
[2024-01-15 10:30:22] INFO: Login successful, navigating to courses
[2024-01-15 10:30:25] INFO: Searching for course: TCS_CODEVITA
[2024-01-15 10:30:27] INFO: Course selected, selecting module
[2024-01-15 10:30:30] INFO: Module selected, clicking test
[2024-01-15 10:30:35] INFO: Test clicked, generating report
[2024-01-15 10:32:45] INFO: Report downloaded: TCS_Test_01.xlsx
[2024-01-15 10:32:45] INFO: Successfully processed TCS_CODEVITA - TCS_Test_01
```

This is what a successful run looks like! 🎉

