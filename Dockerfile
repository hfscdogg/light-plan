# The viewer is one self-contained HTML page, so there is no build stage:
# nothing to bundle, no Node in the image.
FROM python:3.11-slim
WORKDIR /app

# Install poppler (PDF→image) and tesseract (OCR for room label detection)
RUN apt-get update && apt-get install -y --no-install-recommends poppler-utils tesseract-ocr && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/app/ app/

# Copy the viewer into the directory the app serves from
COPY frontend/public/ static/

# Local fallback for DATA_DIR. In production this path should be a mounted
# volume — otherwise the database and uploaded plans die with the container.
RUN mkdir -p data

EXPOSE 8000

ENV PORT=8000

CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
