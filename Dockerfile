FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy pyproject.toml and install Python dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

# Copy application source code
COPY cloudag/ cloudag/
COPY nexusflow/ nexusflow/
COPY README.md .

# Create directory for persistent SQLite database
RUN mkdir -p /app/data
ENV DATABASE_URL="sqlite+aiosqlite:////app/data/cloudag.db"
ENV PYTHONUNBUFFERED=1

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/api/v1/health || exit 1

CMD ["uvicorn", "cloudag.api.server:app", "--host", "0.0.0.0", "--port", "8080"]
