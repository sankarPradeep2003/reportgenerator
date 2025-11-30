# Render Deployment Guide

This guide will help you deploy the Report Generator Flask app to Render.

## Prerequisites

1. Your project is already pushed to a GitHub repository
2. You have a Render account (sign up at https://render.com if needed)

## Step-by-Step Deployment Instructions

### Step 1: Create a New Web Service on Render

1. Log in to your Render dashboard at https://dashboard.render.com
2. Click **"New +"** button
3. Select **"Web Service"**
4. Connect your GitHub account if you haven't already
5. Select the repository containing your project

### Step 2: Configure the Service

Fill in the following settings:

- **Name**: `reportgenerator` (or any name you prefer)
- **Region**: Choose the closest region to your users
- **Branch**: `main` (or your default branch)
- **Root Directory**: `reportgenerator` (since your app is in the reportgenerator folder)
- **Runtime**: `Python 3`
- **Build Command**: 
  ```
  pip install -r requirements.txt && playwright install chromium && playwright install-deps chromium
  ```
- **Start Command**: 
  ```
  gunicorn app:app
  ```

### Step 3: Set Environment Variables

Click on **"Environment"** tab and add these variables:

- **PLAYWRIGHT_HEADLESS**: `true` (required for Render - no display available)
- **RENDER**: `true` (enables Render-specific settings)
- **FLASK_SECRET**: Generate a random secret key (you can use: `python -c "import secrets; print(secrets.token_hex(32))"`)

### Step 4: Deploy

1. Click **"Create Web Service"**
2. Render will start building and deploying your application
3. The build process will:
   - Install Python dependencies
   - Install Playwright and Chromium browser
   - Start your Flask app with Gunicorn
4. Wait for the deployment to complete (this may take 5-10 minutes)

### Step 5: Access Your Application

Once deployed, Render will provide you with a URL like:
`https://reportgenerator.onrender.com`

You can access your application at this URL.

## Important Notes

### Playwright on Render

- The app is configured to run Playwright in **headless mode** on Render (no display)
- Downloads will be saved to `/tmp/downloads` on Render (temporary storage)
- Browser automation will work, but files downloaded won't persist after the service restarts

### Limitations

1. **File Downloads**: Files downloaded during automation are stored in `/tmp/downloads` which is temporary. They will be lost when the service restarts.
2. **Long-running Tasks**: Render free tier has limitations on request timeouts. For batch processing, consider upgrading to a paid plan.
3. **Memory**: Playwright and Chromium require significant memory. Consider using a paid plan for better performance.

### Troubleshooting

If deployment fails:

1. **Check Build Logs**: Look at the build logs in Render dashboard for errors
2. **Playwright Installation**: Ensure the build command includes `playwright install chromium && playwright install-deps chromium`
3. **Python Version**: The `runtime.txt` file specifies Python 3.11.9. Render will use this version.
4. **Port Configuration**: The app automatically uses the `PORT` environment variable provided by Render

### Updating Your Deployment

After pushing changes to GitHub:

1. Render will automatically detect the changes
2. It will trigger a new deployment
3. You can monitor the deployment progress in the Render dashboard

## Files Created for Deployment

The following files were added to support Render deployment:

- **Procfile**: Tells Render how to start your app
- **runtime.txt**: Specifies Python version
- **render.yaml**: Optional configuration file (alternative to manual setup)
- **Updated requirements.txt**: Added gunicorn for production server
- **Updated app.py**: 
  - Uses environment variables for host/port
  - Enables headless mode for Playwright
  - Uses `/tmp/downloads` for file storage on Render

## Next Steps

1. Test your deployed application
2. Monitor the logs in Render dashboard
3. Set up custom domain (optional, paid feature)
4. Configure auto-deploy from your main branch

