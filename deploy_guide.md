# Deployment & Public URL Guide (Step 3 of Submission)

In **Step 3 of 5 ("Submit your bot endpoint")** on the Vera Challenge portal, you must provide a public base URL (e.g., `https://your-bot.example.com`) where these 5 endpoints are reachable:

- `GET  /v1/healthz`
- `GET  /v1/metadata`
- `POST /v1/context`
- `POST /v1/tick`
- `POST /v1/reply`

Below are the 4 easiest ways to get your public URL:

---

## Method 1: Cloudflare Tunnel (Recommended - Free, Instant, No Account Required)

Cloudflare gives you a fast, stable `https://*.trycloudflare.com` URL in 10 seconds.

### Steps:
1. Start your bot locally:
   ```bash
   python run_bot.py
   ```
2. Open a separate terminal and download/run Cloudflare tunnel:
   - On Windows (via winget or direct download):
     ```bash
     winget install Cloudflare.cloudflared
     cloudflared tunnel --url http://localhost:8080
     ```
3. Cloudflare will output a public URL like:
   ```
   https://random-words-here.trycloudflare.com
   ```
4. Copy this base URL and paste it into the **Step 3** input box on the challenge portal.

---

## Method 2: ngrok (Classic & Reliable)

1. Start your bot:
   ```bash
   python run_bot.py
   ```
2. In a second terminal, run:
   ```bash
   ngrok http 8080
   ```
3. Copy the `Forwarding` HTTPS URL (e.g. `https://xxxx-xx-xx.ngrok-free.app`).
4. Paste it as your Base URL in Step 3.

---

## Method 3: localtunnel (Zero Install via npx)

If you have Node.js installed:
```bash
npx localtunnel --port 8080
```
This prints an HTTPS URL. Note that localtunnel may show a one-time IP verification page on the first browser click, but API POST requests pass through directly.

---

## Method 4: 1-Click Free Cloud Deployment (24/7 Uptime)

If you want your bot hosted in the cloud without leaving your local computer running:

### A. Render (render.com):
1. Push this folder to a GitHub repository.
2. In Render dashboard, click **New +** → **Web Service**.
3. Select your repo.
4. Settings:
   - **Environment**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python run_bot.py`
5. Render generates a public URL: `https://<service-name>.onrender.com`.

### B. Railway (railway.app):
1. Click **New Project** → **Deploy from GitHub repo**.
2. Railway auto-detects `Dockerfile` or `requirements.txt`.
3. In settings, click **Generate Domain** → copy your `https://*.up.railway.app` URL.

---

## Verifying Your Live Endpoint Before Submitting

Once you have your public base URL (e.g. `https://my-bot.trycloudflare.com`), test it in your terminal or browser:

```bash
# Check health
curl https://my-bot.trycloudflare.com/v1/healthz

# Check metadata
curl https://my-bot.trycloudflare.com/v1/metadata
```

Expected response for `/v1/healthz`:
```json
{
  "status": "ok",
  "uptime_seconds": 45,
  "contexts_loaded": {
    "category": 5,
    "merchant": 50,
    "customer": 200,
    "trigger": 100
  }
}
```

Once verified, click **Next** in the portal!
