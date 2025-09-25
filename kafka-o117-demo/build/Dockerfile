# Dockerfile for ICCP Simulator
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY iccp_simulator.py .
COPY health_check.py .

RUN mkdir -p /app/config

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

RUN useradd --create-home --shell /bin/bash iccp && \
    chown -R iccp:iccp /app

USER iccp

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python health_check.py

EXPOSE 8080

CMD ["python", "iccp_simulator.py"]