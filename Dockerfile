# ============================================================
# Dockerfile
#
# Builds the InsightAI FastAPI backend image.
# Referenced by docker-compose.yml's "backend" service.
# ============================================================

FROM python:3.11-slim

# ---------- Environment Configuration ----------
# Prevents Python from writing .pyc files and buffering stdout/stderr,
# which keeps container logs showing up in real time.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# ---------- System Dependencies ----------
# build-essential + default-libmysqlclient-dev are needed to compile
# certain Python packages with C extensions (e.g. some SQLAlchemy/MySQL
# driver dependencies) on Debian-based images.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    default-libmysqlclient-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# ---------- Python Dependencies ----------
# Copying only requirements.txt first (before the rest of the code) lets
# Docker cache this layer — dependencies only get reinstalled when
# requirements.txt actually changes, not on every code edit.
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ---------- Application Code ----------
COPY backend/ ./backend/
COPY static/ ./static/
COPY database/ ./database/

# ---------- Runtime Directories ----------
# Created explicitly so the app doesn't fail on first upload/report/chart
# if these directories don't already exist as volumes.
RUN mkdir -p uploads reports models charts

# ---------- Non-Root User ----------
# Running as a dedicated non-root user is a security best practice —
# limits the blast radius if the container is ever compromised.
RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# ---------- Healthcheck ----------
# Lets Docker (and orchestrators like Render/Railway) know if the
# container is actually serving requests, not just running.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/')" || exit 1

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]