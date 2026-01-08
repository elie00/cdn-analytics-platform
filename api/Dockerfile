FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY routing_service.py .

# Create data directory for GeoIP databases
RUN mkdir -p /data

# Download GeoIP databases (Lite version - gratuite)
# En production, utiliser MaxMind GeoIP2
RUN curl -sL "https://git.io/GeoLite2-City.mmdb" -o /data/GeoLite2-City.mmdb || echo "GeoIP download skipped"
RUN curl -sL "https://git.io/GeoLite2-ASN.mmdb" -o /data/GeoLite2-ASN.mmdb || echo "ASN download skipped"

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8080/health || exit 1

# Expose port
EXPOSE 8080

# Run with gunicorn for production
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "4", "--threads", "2", "--timeout", "60", "--access-logfile", "-", "--error-logfile", "-", "routing_service:app"]
