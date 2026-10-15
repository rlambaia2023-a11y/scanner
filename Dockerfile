FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    OMP_THREAD_LIMIT=1

# Tesseract com português (OCR) + bibliotecas que o OpenCV precisa
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-por libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY scanner.py bot.py ./

RUN useradd --create-home --uid 10001 scanner && chown -R scanner /app
USER scanner

CMD ["python", "bot.py"]
