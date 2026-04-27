FROM python:3.11-slim

# Install Node.js for frontend build
RUN apt-get update && apt-get install -y nodejs npm && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Build React frontend
COPY frontend/ frontend/
RUN cd frontend && npm install && npm run build

# Backend
COPY backend/ backend/
RUN mkdir -p backend/static/photos

EXPOSE 7860

CMD ["sh", "-c", "cd /app/backend && uvicorn main:app --host 0.0.0.0 --port ${PORT:-7860}"]
