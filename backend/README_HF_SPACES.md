# CaptionForge Backend — HF Spaces Setup

## Environment Variables (HF Spaces → Settings → Variables)

Set these on your HF Space before deploying. Variables marked **Required** will break the app if missing.

---

### YouTube Relay (for YouTube URL feature)

| Variable | Required | Example value | Notes |
|---|---|---|---|
| `RELAY_URL` | **Required** | `https://captionforge-relay.fly.dev` | Base URL of your Fly.io relay service. No trailing slash. Without this, YouTube URL downloads fall back to local yt-dlp which will fail on HF datacenter IPs. |
| `RELAY_SECRET_KEY` | **Required** | `some-long-random-string` | Shared secret between HF Spaces and the relay. Must match `RELAY_SECRET_KEY` set via `fly secrets set` on the relay. Generate with: `python -c "import secrets; print(secrets.token_hex(32))"` |

---

### AI Transcript Enhancement

| Variable | Required | Example value | Notes |
|---|---|---|---|
| `OPENROUTER_API_KEY` | **Required** | `sk-or-v1-...` | Your OpenRouter API key. Get one at openrouter.ai. Used for Gemma 3:12B transcript enhancement. |
| `OPENROUTER_MODEL` | Optional | `google/gemma-3-12b-it` | Default is already `google/gemma-3-12b-it`. Only change if you want a different model. |
| `OPENROUTER_BASE_URL` | Optional | `https://openrouter.ai/api/v1` | Only change if using a self-hosted OpenRouter-compatible API. |

---

### Whisper ASR

| Variable | Required | Default | Notes |
|---|---|---|---|
| `WHISPER_MODEL` | Optional | `base` | Model size: `tiny`, `base`, `small`, `medium`, `large-v3`. Larger = slower but more accurate. `base` is recommended for the free CPU tier. |
| `WHISPER_DEVICE` | Optional | `cpu` | `cpu` or `cuda`. HF Spaces free tier has no GPU, use `cpu`. |
| `WHISPER_COMPUTE_TYPE` | Optional | `int8` | `int8` for CPU (fastest), `float16` for GPU. |

---

### Optional — yt-dlp local fallback (only used when RELAY_URL is not set)

These only matter during local development. They are ignored when `RELAY_URL` is set.

| Variable | Notes |
|---|---|
| `YTDLP_COOKIES_FILE` | Path to a Netscape cookies file (local dev only) |
| `YOUTUBE_COOKIES` | Raw Netscape cookie text as an env var (local dev only) |

---

## How to set variables on HF Spaces

1. Go to your Space: `https://huggingface.co/spaces/Gurshameer/CaptionForge-API`
2. Click **Settings** tab
3. Scroll to **Repository secrets** (or **Variables**)
4. Click **New secret** for each variable above
5. After adding all secrets, click **Restart Space** (or push a commit to trigger redeploy)

---

## Deployment flow

```
Local repo (GitHub)
    ↓  push to main  (backend/** path trigger)
GitHub Actions: deploy-backend.yml
    ↓  git push --force to HF Space remote
HF Space rebuilds Docker image, starts uvicorn
    ↓  requests to /api/v1/subtitles/url
CaptionForge backend
    ↓  POST /extract  (with X-Relay-Key header)
Fly.io relay (captionforge-relay.fly.dev)
    ↓  runs yt-dlp on clean IP
    ↓  streams .mp3 back
HF Space backend saves file, runs Whisper, returns .srt
```

---

## Quick health checks after redeploying

```bash
# 1. Backend alive?
curl https://Gurshameer-CaptionForge-API.hf.space/

# 2. Relay alive?
curl https://captionforge-relay.fly.dev/health

# 3. End-to-end YouTube download via relay:
curl -X POST https://captionforge-relay.fly.dev/extract \
  -H "X-Relay-Key: YOUR_RELAY_SECRET_KEY" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://www.youtube.com/watch?v=9PXluC2FMD0"}' \
  --output test.mp3 --progress-bar
# Expected: test.mp3 appears and has non-zero size
```
