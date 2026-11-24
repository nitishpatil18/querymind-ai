# Build from the repository root:  docker build -f backend/Dockerfile .  (docker-compose does this)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/hf \
    DATA_DIR=/data

WORKDIR /app

# CPU-only PyTorch keeps the image small (no CUDA libraries needed for MiniLM).
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu

COPY backend/requirements.txt .
RUN pip install -r requirements.txt

# Bake the embedding model into the image so the container never downloads it at runtime.
ARG PRELOAD_EMBEDDING_MODEL=1
ARG EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
RUN if [ "$PRELOAD_EMBEDDING_MODEL" = "1" ]; then \
      python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${EMBEDDING_MODEL}')"; \
    fi

COPY backend/app ./app
COPY backend/scripts ./scripts
COPY backend/evaluation ./evaluation
COPY database/init /database/init

RUN useradd --create-home --uid 10001 appuser && mkdir -p /data && chown -R appuser /data /app
USER appuser
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=60s --retries=5 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
