# Relay Deployment Guide — Render.com

We use a tiny Render web service to act as a YouTube proxy. Since it's incredibly lightweight and fast, Render's free tier sleep/wake cycle (spin-down) is not a problem here like it was for the main app.

## Prerequisites

- A free account on [Render.com](https://render.com)
- Your code must be pushed to GitHub

---

## Step 1 — Push your changes to GitHub

Since you've switched from Fly.io to Render, we've updated the `render.yaml` at the root of the project to point to the `relay` folder.

```bash
git add render.yaml relay/requirements.txt relay/main.py relay/DEPLOY.md relay/fly.toml relay/Dockerfile
git commit -m "chore: pivot relay deployment to Render.com"
git push origin main
```

*(Note: We can delete `fly.toml` and `Dockerfile` if we want, as Render uses native Python environments).*

---

## Step 2 — Deploy on Render

1. Go to the [Render Dashboard](https://dashboard.render.com).
2. Click **New +** → **Blueprint**.
3. Connect your repository (`Gurshameer/CaptionForge`).
4. Render will automatically detect the `render.yaml` file.
5. Click **Apply**.

---

## Step 3 — Set the Secret Key

While it's deploying:

1. Click on the new **captionforge-relay** service in your Render dashboard.
2. Go to **Environment** (left sidebar).
3. Click **Add Environment Variable**.
4. Key: `RELAY_SECRET_KEY`
5. Value: Generate a random string. (For example, run `python -c "import secrets; print(secrets.token_hex(32))"` in your terminal and paste the result).
6. Click **Save Changes**. (This will trigger a new deploy).

---

## Step 4 — Test the deployed relay (BEFORE touching HF Spaces)

Once the service is completely deployed and live, grab the URL from the top of the Render dashboard (e.g., `https://captionforge-relay.onrender.com`).

Run this in your terminal:

```bash
# Replace YOUR_RELAY_URL and YOUR_RELAY_SECRET_KEY
curl -X POST https://YOUR_RELAY_URL/extract \
  -H "X-Relay-Key: YOUR_RELAY_SECRET_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"url\":\"https://www.youtube.com/watch?v=9PXluC2FMD0\"}" \
  --output test.mp3 \
  --progress-bar

# ✅ SUCCESS: test.mp3 has non-zero size and plays
```

---

## Step 5 — Point HF Spaces to the Relay

Go to: `https://huggingface.co/spaces/Gurshameer/CaptionForge-API` → **Settings** → **Variables**

Add or update these secrets:

| Variable | Value |
|---|---|
| `RELAY_URL` | `https://captionforge-relay.onrender.com` (Your Render URL) |
| `RELAY_SECRET_KEY` | *(same value you set in Step 3)* |
| `OPENROUTER_API_KEY` | *(your OpenRouter API key)* |

---

## Step 6 — Restart the HF Space

After adding the environment variables, trigger a restart:

**Option A (recommended):** Push a trivial commit to the `backend/` folder — GitHub Actions will redeploy to HF Spaces automatically.

**Option B (manual):** On HF Spaces → Settings → scroll to **"Factory reboot"** and click it.
