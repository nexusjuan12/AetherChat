FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . ./

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /data/output /data/private/voice-samples \
    && chown -R appuser:appuser /app /data

USER appuser
EXPOSE 8081
CMD ["gunicorn", "--workers", "2", "--threads", "4", "--bind", "0.0.0.0:8081", "webserver:app"]
