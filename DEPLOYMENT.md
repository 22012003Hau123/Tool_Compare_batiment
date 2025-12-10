# Deployment Guide - Streamlit Community Cloud

## 🚀 Deploy to Streamlit Cloud (FREE)

### Prerequisites
- GitHub account
- Repository pushed to GitHub ✅ (Done!)

### Steps

#### 1. Go to Streamlit Cloud
Visit: https://streamlit.io/cloud

#### 2. Sign in with GitHub
- Click "Sign up" or "Sign in"
- Choose "Continue with GitHub"
- Authorize Streamlit to access your repos

#### 3. Create New App
- Click "New app" button
- Select repository: `22012003Hau123/Tool_Compare_batiment`
- Branch: `main`
- Main file path: `streamlit_app.py`

#### 4. Configure Secrets (for Mode 2)
If using Mode 2 GPT verification:

**In Streamlit Cloud dashboard:**
- Click "Advanced settings"
- Add to "Secrets" section:
```toml
OPENAI_API_KEY = "sk-your-actual-key-here"
GPT_MODEL = "gpt-4o-mini"
```

#### 5. Deploy!
- Click "Deploy!"
- Wait 2-3 minutes for initial build
- App will be live at: `https://[your-app-name].streamlit.app`

### ✅ Done!
Your app is now online and accessible to anyone!

---

## 📝 Important Notes

### File Upload
- Streamlit Cloud has 200MB file size limit
- Large PDFs work but may be slow
- Consider compression for very large files

### API Keys
- **Never commit API keys to GitHub!**
- Use Streamlit Cloud Secrets (as shown above)
- Or users can input their own API key in the app

### Auto Redeploy
- Push to GitHub → Auto redeploy
- Usually takes 1-2 minutes
- Check deployment logs for errors

### Free Tier Limits
- Max 3 apps
- 1GB RAM per app
- Auto-sleep after inactivity (wakes on visit)
- Perfect for this use case

---

## 🔧 Alternative: GitHub Codespaces

If you want a development environment online:

1. Go to your GitHub repo
2. Click "Code" → "Codespaces" → "Create codespace"
3. Wait for container to build
4. In terminal:
   ```bash
   pip install -r requirements.txt
   streamlit run streamlit_app.py
   ```
5. Click "Open in Browser" when prompted

**Note:** Codespaces free tier = 60 hours/month

---

## 📱 Share Your App

Once deployed on Streamlit Cloud:
- Share URL: `https://your-app.streamlit.app`
- No installation needed for users
- Works on mobile browsers too!

---

## 🐛 Troubleshooting

### Build fails?
- Check `requirements.txt` has all dependencies
- Ensure Python version compatibility (3.8-3.11)
- Review deployment logs in Streamlit Cloud

### App crashes?
- Check file paths (use relative paths)
- Verify temp directory handling
- Check memory usage (large PDFs)

### API errors?
- Verify Secrets configuration
- Check API key validity
- Monitor API usage/limits

---

## 🎯 Recommended Setup

For production use:

1. **Deploy to Streamlit Cloud** - Main public access
2. **Keep local version** - Development and testing
3. **Use GitHub** - Version control and auto-deploy
4. **Add README** - Usage instructions for users
5. **Monitor logs** - Check for errors/usage

Your app is ready for the world! 🌍
