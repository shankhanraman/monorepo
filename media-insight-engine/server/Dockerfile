FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FASTEMBED_CACHE_PATH=/opt/fastembed \
    EMBED_MODEL=BAAI/bge-small-en-v1.5 \
    WHISPER_DIR=/opt/whisper \
    WHISPER_MODEL=large-v3-turbo

WORKDIR /app

COPY requirements.txt .
# crawl4ai-setup installs Playwright's Chromium and the OS libraries it needs.
RUN pip install --no-cache-dir -r requirements.txt \
 && crawl4ai-setup \
 && rm -rf /var/lib/apt/lists/*

# Bake the embedding model into the image so the first sync doesn't download it.
RUN python -c "import os; from fastembed import TextEmbedding; TextEmbedding(os.environ['EMBED_MODEL'], cache_dir=os.environ['FASTEMBED_CACHE_PATH'])"
# Speech-to-text model (Day 2). Override with WHISPER_MODEL in .env (e.g. small.en); other models download on first use.
RUN python -c "import os; from faster_whisper import WhisperModel; WhisperModel(os.environ['WHISPER_MODEL'], device='cpu', compute_type='int8', download_root=os.environ['WHISPER_DIR'])"

COPY . .

EXPOSE 8003
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003"]
