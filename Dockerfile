# Stage 1: Build frontend
FROM node:22-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Python backend with frontend static files
FROM python:3.11-slim
WORKDIR /app

# Install poppler for PDF-to-image conversion
RUN apt-get update && apt-get install -y --no-install-recommends poppler-utils && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/app/ app/

# Copy built frontend into backend static directory
COPY --from=frontend-build /app/frontend/dist/ static/

# Create uploads directory
RUN mkdir -p uploads

EXPOSE 8000

ENV PORT=8000

CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
