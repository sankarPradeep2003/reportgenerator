# Render Deployment - Step by Step Checklist

## ✅ Pre-Deployment Checklist

- [x] Updated `app.py` to use Render's PORT environment variable
- [x] Created `build.sh` for Playwright browser installation
- [x] Created `render.yaml` for automated deployment (optional)
- [x] Created `.gitignore` to exclude unnecessary files
- [x] Created deployment documentation

---

## 📋 Step-by-Step Deployment

### **STEP 1: Prepare Your Code**

1. Make sure all files are saved
2. Initialize Git (if not already done):
   ```bash
   git init
   git add .
   git commit -m "Initial commit for Render deployment"
   ```

### **STEP 2: Push to GitHub**

1. Create a new repository on GitHub:
   - Go to https://github.com/new
   - Name it: `reportgenerator` (or any name)
   - **Don't** initialize with README, .gitignore, or license
   - Click "Create repository"

2. Push your code:
   ```bash
   git remote add origin https://github.com/YOUR_USERNAME/reportgenerator.git
   git branch -M main
   git push -u origin main
   ```
   Replace `YOUR_USERNAME` with your actual GitHub username.

### **STEP 3: Sign Up for Render**

1. Go to https://render.com
2. Click "Get Started for Free"
3. Sign up using GitHub (recommended) or email

### **STEP 4: Create Web Service**

1. In Render dashboard, click **"New +"** (top right)
2. Select **"Web Service"**
3. If prompted, connect your GitHub account and authorize Render

### **STEP 5: Connect Repository**

1. Select your repository: `reportgenerator` (or whatever you named it)
2. Click **"Connect"**

### **STEP 6: Configure Service Settings**

Fill in these exact values:

#### **Basic Information:**
- **Name**: `reportgenerator` (or your preferred name)
- **Region**: Choose closest to your users
- **Branch**: `main`
- **Root Directory**: Leave empty

#### **Build & Deploy:**
- **Environment**: `Python 3`
- **Build Command**: 
  ```
  chmod +x build.sh && ./build.sh
  ```
- **Start Command**: 
  ```
  python app.py
  ```

#### **Environment Variables:**
Click "Add Environment Variable" for each:

1. **FLASK_SECRET**
   - Click the "Generate" button to auto-generate
   - OR manually enter a random string

2. **FLASK_ENV**
   - Value: `production`

3. **PYTHON_VERSION** (optional)
   - Value: `3.11.0`

#### **Advanced Settings:**
- **Auto-Deploy**: `Yes` ✅
- **Health Check Path**: `/`

### **STEP 7: Deploy**

1. Scroll down and click **"Create Web Service"**
2. Render will start building your application
3. **Wait 5-10 minutes** for the first deployment
   - Installing Playwright browsers takes time
   - Watch the build logs for progress

### **STEP 8: Verify Deployment**

1. Once you see a green checkmark ✅, deployment is complete
2. Your app URL will be: `https://reportgenerator.onrender.com`
3. Click the URL to test your application
4. Try submitting a report generation request

---

## 🔧 Troubleshooting

### Build Fails?
- Check build logs for error messages
- Ensure `build.sh` is in your repository
- Verify `requirements.txt` is correct

### App Won't Start?
- Check runtime logs
- Verify environment variables are set
- Ensure `FLASK_SECRET` is configured

### Playwright Issues?
- First build takes longer (browsers download)
- If timeout, try redeploying
- Check that `build.sh` executed successfully

### Service Spins Down?
- Normal on free tier (15 min inactivity)
- First request after spin-down is slow (~30-60 sec)
- Consider paid plan for always-on service

---

## 📝 After Deployment

### Update Your Application:
```bash
# Make changes locally
git add .
git commit -m "Update message"
git push origin main
# Render auto-deploys on push!
```

### View Logs:
- Go to Render dashboard
- Click on your service
- Click "Logs" tab

### Monitor Health:
- Check "Metrics" tab for performance
- Set up alerts if needed

---

## 🎉 Success!

Your Report Generator is now live! Share the URL with your users.

**Need Help?**
- See [DEPLOYMENT.md](./DEPLOYMENT.md) for detailed guide
- Check Render docs: https://render.com/docs
- Render community: https://community.render.com

