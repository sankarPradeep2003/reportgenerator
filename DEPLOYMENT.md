# Deployment Guide for Render

This guide will walk you through deploying your Report Generator application to Render step by step.

## Prerequisites

1. A GitHub account
2. Your code pushed to a GitHub repository
3. A Render account (sign up at https://render.com if you don't have one)

---

## Step-by-Step Deployment Instructions

### Step 1: Prepare Your Code Repository

1. **Initialize Git** (if not already done):
   ```bash
   git init
   git add .
   git commit -m "Initial commit - ready for Render deployment"
   ```

2. **Create a GitHub Repository**:
   - Go to https://github.com/new
   - Create a new repository (e.g., `reportgenerator`)
   - **Do NOT** initialize with README, .gitignore, or license

3. **Push Your Code to GitHub**:
   ```bash
   git remote add origin https://github.com/YOUR_USERNAME/reportgenerator.git
   git branch -M main
   git push -u origin main
   ```
   Replace `YOUR_USERNAME` with your GitHub username.

---

### Step 2: Sign Up / Log In to Render

1. Go to https://render.com
2. Sign up for a free account (or log in if you already have one)
3. You can sign up using your GitHub account for easier integration

---

### Step 3: Create a New Web Service

1. **Navigate to Dashboard**:
   - Once logged in, click on "New +" button in the top right
   - Select "Web Service"

2. **Connect Your Repository**:
   - Click "Connect account" if you haven't connected GitHub
   - Authorize Render to access your GitHub repositories
   - Select your repository (`reportgenerator`)

---

### Step 4: Configure Your Service

Fill in the following settings:

#### Basic Settings:
- **Name**: `reportgenerator` (or any name you prefer)
- **Region**: Choose the closest region to your users
- **Branch**: `main` (or your default branch)
- **Root Directory**: Leave empty (or `.` if your files are in root)

#### Build & Deploy:
- **Environment**: `Python 3`
- **Build Command**: 
  ```bash
  chmod +x build.sh && ./build.sh
  ```
- **Start Command**: 
   ```bash
   gunicorn app:app
   ```

#### Environment Variables:
Click "Add Environment Variable" and add:

1. **FLASK_SECRET**:
   - Click "Generate" to auto-generate a secure secret key
   - Or manually enter a random string (e.g., `your-secret-key-here`)

2. **FLASK_ENV**:
   - Value: `production`

3. **PYTHON_VERSION** (optional):
   - Value: `3.11.0`

4. **HEADLESS** (optional but recommended):
   - Value: `true`
   - This ensures Playwright runs in headless mode on the server
   - The app will auto-detect, but this makes it explicit

#### Advanced Settings (Optional):
- **Auto-Deploy**: `Yes` (deploys automatically on git push)
- **Health Check Path**: `/` (your root URL)

---

### Step 5: Deploy

1. **Review Settings**: Double-check all your settings
2. **Click "Create Web Service"**: Render will start building your application
3. **Monitor the Build**: 
   - You'll see build logs in real-time
   - The build process will:
     - Install Python dependencies
     - Install Playwright browsers (this may take a few minutes)
     - Start your application

---

### Step 6: Wait for Deployment

1. **Build Time**: First deployment typically takes 5-10 minutes
   - Installing Playwright browsers is the longest step
2. **Watch the Logs**: 
   - Green checkmark = successful deployment
   - Red X = build failed (check logs for errors)

---

### Step 7: Access Your Application

1. Once deployed, Render will provide you with a URL like:
   ```
   https://reportgenerator.onrender.com
   ```
2. **Test Your Application**:
   - Open the URL in your browser
   - You should see your Report Generator interface
   - Test the functionality

---

## Important Notes

### Free Tier Limitations:
- **Spinning Down**: Free tier services spin down after 15 minutes of inactivity
- **First Request**: May take 30-60 seconds to wake up
- **Memory**: Limited to 512MB RAM
- **CPU**: Shared CPU resources

### Playwright on Render:
- Playwright browsers are installed during the build process
- The build script (`build.sh`) handles this automatically
- First build may take longer due to browser downloads
- **Note**: Playwright requires Node.js >=18, which Render automatically provides

### Environment Variables:
- `FLASK_SECRET`: Used for Flask session security (auto-generated)
- `PORT`: Automatically set by Render (don't override)
- `HOST`: Automatically set to `0.0.0.0` (don't override)

---

## Troubleshooting

### Build Fails:
1. **Check Build Logs**: Look for error messages
2. **Common Issues**:
   - Missing dependencies in `requirements.txt`
   - Playwright installation timeout (retry the build)
   - Python version mismatch

### Application Won't Start:
1. **Check Runtime Logs**: Look for Python errors
2. **Verify Start Command**: Should be `python app.py`
3. **Check Environment Variables**: Ensure `FLASK_SECRET` is set

### Playwright Not Working:
1. **Verify Build Script**: Ensure `build.sh` is executable
2. **Check Logs**: Look for Playwright installation messages
3. **Re-deploy**: Sometimes a fresh deployment fixes issues

### Service Spins Down:
- This is normal on the free tier
- First request after spin-down will be slow
- Consider upgrading to a paid plan for always-on service

---

## Updating Your Application

1. **Make Changes Locally**
2. **Commit and Push**:
   ```bash
   git add .
   git commit -m "Your update message"
   git push origin main
   ```
3. **Auto-Deploy**: Render will automatically detect the push and redeploy
4. **Monitor**: Watch the deployment logs in Render dashboard

---

## Next Steps

- **Custom Domain**: Add your own domain in Render settings
- **Upgrade Plan**: Consider paid plans for better performance
- **Monitoring**: Set up health checks and alerts
- **Backups**: Consider database storage for file metadata (currently in-memory)

---

## Support

- **Render Docs**: https://render.com/docs
- **Render Community**: https://community.render.com
- **Your App Logs**: Available in Render dashboard

---

**Congratulations!** Your Report Generator is now live on Render! 🎉

