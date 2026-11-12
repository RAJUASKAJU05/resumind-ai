FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
COPY static static
ENV DB_PATH=/data/resumind.db COOKIE_SECURE=1
RUN mkdir -p /data
# WEB_CONCURRENCY controls how many worker processes handle requests. It defaults to 1, which is
# the only safe value right now: the rate limiter and CAPTCHA store are in-memory, and uvicorn
# spreads requests across workers round-robin (not sticky per user), so a CAPTCHA issued by one
# worker can land on a different worker on the next request and fail to verify. Raising this above
# 1 needs that state moved into the database first — see README "Scaling beyond one process".
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${WEB_CONCURRENCY:-1}"]
