# LeadDesk — one image, one command.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# Tesseract is the OCR engine; without it scans cannot be read.
RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY static ./static
COPY scripts ./scripts
COPY sample_data ./sample_data
COPY docs ./docs

# data/ (database + encrypted blobs) and secrets/ (vault master key) are volumes,
# not part of the image, so the key never ships inside a build.
RUN mkdir -p /app/data /app/secrets

ENV DATA_DIR=/app/data \
    VAULT_MASTER_KEY_FILE=/app/secrets/vault_master.key \
    VAULT_AUTOCREATE_KEY=1 \
    SEED_DEMO=1 \
    DEMO_MODE=1 \
    OLLAMA_URL=http://host.docker.internal:11434 \
    SMTP_HOST=mailpit \
    SMTP_PORT=1025

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import os,urllib.request,sys; p=os.environ.get('PORT','8000'); sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:{p}/api/health', timeout=4).status == 200 else 1)"

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
