# ── Base Image ────────────────────────────────────────────────
FROM python:3.12-slim

# ── Environment ───────────────────────────────────────────────
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# ── Working Directory ─────────────────────────────────────────
WORKDIR /app

# ── System Dependencies ───────────────────────────────────────
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
        python3-dev \
    && rm -rf /var/lib/apt/lists/*

# ── Install Python Dependencies ───────────────────────────────
COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ── Copy Project ──────────────────────────────────────────────
COPY . .

# ── Expose Port ───────────────────────────────────────────────
EXPOSE 8000