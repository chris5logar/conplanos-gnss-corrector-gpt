FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=America/Lima

RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-spa tesseract-ocr-eng \
    fonts-dejavu-core ca-certificates tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN python -m pip install -r requirements.txt && python -m pip check

RUN groupadd --gid 1000 conplanos \
    && useradd --uid 1000 --gid 1000 --create-home conplanos
COPY --chown=conplanos:conplanos . .
USER conplanos

EXPOSE 10000
CMD ["python", "start_render.py"]
