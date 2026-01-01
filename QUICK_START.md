# Quick Start - Deploy to Render

## TL;DR - Fastest Way

1. **Push to GitHub**:
   ```bash
   git init
   git add .
   git commit -m "Ready for Render"
   git remote add origin https://github.com/YOUR_USERNAME/reportgenerator.git
   git push -u origin main
   ```

2. **Deploy on Render**:
   - Go to https://render.com
   - Click "New +" → "Web Service"
   - Connect your GitHub repo
   - Use these settings:
     - **Build Command**: `chmod +x build.sh && ./build.sh`
     - **Start Command**: `python app.py`
     - **Environment Variables**:
       - `FLASK_SECRET`: Generate (click Generate button)
       - `FLASK_ENV`: `production`
   - Click "Create Web Service"
   - Wait 5-10 minutes for first deployment

3. **Done!** Your app will be live at `https://your-app-name.onrender.com`

---

## Detailed Instructions

See [DEPLOYMENT.md](./DEPLOYMENT.md) for complete step-by-step guide.

