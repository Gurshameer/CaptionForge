# Relay Deployment Guide — Fly.io

## Prerequisites

- `flyctl` installed ([install guide](https://fly.io/docs/hands-on/install-flyctl/))
- A Fly.io account (free tier is enough)
- Run all commands **from the `relay/` directory**

---

## Step 1 — Test the relay locally FIRST

Before deploying anywhere, verify yt-dlp works on your machine:

```bash
# From relay/ directory
pip install -r requirements.txt
RELAY_SECRET_KEY=testsecret uvicorn main:app --port 8080 --reload
```

In another terminal:
```bash
curl -X POST http://localhost:8080/extract \
  -H "X-Relay-Key: testsecret" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://www.youtube.com/watch?v=9PXluC2FMD0"}' \
  --output test_local.mp3 --progress-bar

# Expected: test_local.mp3 appears, non-zero size
```

---

## Step 2 — Deploy to Fly.io

```bash
# 1. Authenticate
fly auth login

# 2. Create the app (only needed once — skips interactive prompt)
fly launch \
  --name captionforge-relay \
  --region iad \
  --no-deploy \
  --copy-config

# 3. Set the secret key (generated securely — use your own value)
#    This must match RELAY_SECRET_KEY you set on HF Spaces
fly secrets set RELAY_SECRET_KEY="$(python -c "import secrets; print(secrets.token_hex(32))")"

# 4. Deploy
fly deploy

# 5. Check it's live
fly status
fly logs
```

> The app name `captionforge-relay` in `fly.toml` means your URL will be:
> `https://captionforge-relay.fly.dev`

---

## Step 3 — Test the deployed relay (BEFORE touching HF Spaces)

```bash
# Replace YOUR_RELAY_SECRET_KEY with the value you set in Step 2
curl -X POST https://captionforge-relay.fly.dev/extract \
  -H "X-Relay-Key: YOUR_RELAY_SECRET_KEY" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://www.youtube.com/watch?v=9PXluC2FMD0"}' \
  --output test.mp3 \
  --progress-bar

# ✅ SUCCESS: test.mp3 has non-zero size and plays
# ❌ FAIL: If you get SSL: UNEXPECTED_EOF, Fly.io's IP is also blocked.
#           Try a different region: fly regions add lhr && fly deploy
```

Also test the health endpoint:
```bash
curl https://captionforge-relay.fly.dev/health
# Expected: {"status":"ok"}
```

---

## Step 4 — Set env vars on HF Spaces

Go to: `https://huggingface.co/spaces/Gurshameer/CaptionForge-API` → **Settings** → **Variables**

Add these secrets:

| Variable | Value |
|---|---|
| `RELAY_URL` | `https://captionforge-relay.fly.dev` |
| `RELAY_SECRET_KEY` | *(same value you set with `fly secrets set`)* |
| `OPENROUTER_API_KEY` | *(your OpenRouter API key)* |

---

## Step 5 — Restart the HF Space

After adding env vars, trigger a restart:

**Option A (recommended):** Push a trivial commit to the `backend/` folder — GitHub Actions will redeploy to HF Spaces automatically.

**Option B (manual):** On HF Spaces → Settings → scroll to **"Factory reboot"** and click it.

---

## Useful Fly.io commands

```bash
# View live logs
fly logs --app captionforge-relay

# Open a shell inside the machine
fly ssh console --app captionforge-relay

# Scale up if needed (e.g., for testing)
fly scale memory 512 --app captionforge-relay

# Update the secret key
fly secrets set RELAY_SECRET_KEY="new-secret-here" --app captionforge-relay

# Redeploy (after code changes)
fly deploy

# Destroy the app
fly apps destroy captionforge-relay
```

---

## Log patterns to look for

### Successful YouTube download via relay:
```
[extract] Received request | url=https://youtube.com/watch?v=...
[extract] Running yt-dlp for: https://...
[extract] Download complete: audio.mp3 (4821 KB) — streaming back
[extract] Sending response: tmpXXXXXX.mp3
[cleanup] Deleted temp file: tmpXXXXXX.mp3
```

### Auth failure (wrong RELAY_SECRET_KEY):
```
[auth] Invalid X-Relay-Key: 'wrong-key'
→ HTTP 401 returned to caller
```

### yt-dlp blocked (Fly.io IP also blocked by YouTube):
```
[extract] yt-dlp failed (rc=1): ERROR: unable to download webpage: ... SSL: UNEXPECTED_EOF
→ HTTP 502 returned to caller
```
If you see this, try a different Fly.io region:
```bash
fly regions add lhr    # London
fly deploy
```
