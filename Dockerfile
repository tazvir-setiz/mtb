FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DATABASE_URL=sqlite:////data/forwarder.db \
    TELETHON_SESSION=/data/forwarder_session \
    LOG_TO_FILE=false \
    PROXY_ENABLED=false

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY main.py ./

# Railway attaches the persistent volume at /data at runtime.
# Run the Python process directly so it receives Railway's SIGTERM.
CMD ["python", "-u", "main.py"]
