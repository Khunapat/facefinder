# ---------- build stage: compile any wheels that need a toolchain ----------
FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 HOME=/home/appuser
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential python3-dev \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN mkdir -p $HOME && pip install --user -r requirements.txt


# ---------- runtime stage ----------
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

# libglib/libgomp are what opencv and onnxruntime need even in headless builds
RUN apt-get update && apt-get install -y --no-install-recommends \
      libglib2.0-0 libgomp1 curl \
 && rm -rf /var/lib/apt/lists/*

# Hugging Face Spaces (and most hosts) run containers as a non-root user.
RUN useradd -m -u 1000 appuser
USER appuser
ENV HOME=/home/appuser PATH=/home/appuser/.local/bin:$PATH
COPY --from=builder --chown=appuser /home/appuser/.local /home/appuser/.local

WORKDIR /home/appuser/app
COPY --chown=appuser app ./app

# DATA_DIR holds the model files and the embedding cache. Point it at a mounted
# volume if the host offers one; otherwise the index rebuilds after a restart.
ENV DATA_DIR=/home/appuser/data
RUN mkdir -p $DATA_DIR

# Bake the face model into the image so the first scan is not slow.
RUN python -c "from app import faces; e = faces.engine(); print('face engine:', e.name)"

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD curl -fs http://localhost:${PORT:-8000}/healthz || exit 1
CMD ["sh","-c","uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
