FROM python:3.11-slim

# Install ffmpeg (required by yt-dlp for audio conversion to mp3)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Non-root user for security
RUN useradd -m -u 1000 relay
USER relay
ENV PATH="/home/relay/.local/bin:$PATH"

WORKDIR /app

# Install Python dependencies
COPY --chown=relay:relay requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Copy application code
COPY --chown=relay:relay . .

# Fly.io injects PORT; default to 8080 for local testing
ENV PORT=8080

EXPOSE 8080

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
