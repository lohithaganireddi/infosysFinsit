# ==============================================================================
# FinSight - Production Google Cloud Run Dockerfile
# ==============================================================================
FROM python:3.11-slim

# Prevent Python from writing bytecode and buffering stdout/stderr
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080 \
    FLASK_ENV=production

WORKDIR /app

# Install system libraries needed for ReportLab / Pillow / PostgreSQL client
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install pinned Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

# Ensure runtime directories exist
RUN mkdir -p instance static/uploads

# Expose default container port
EXPOSE 8080

# Start production WSGI server (Gunicorn with multi-threading)
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 app:app
