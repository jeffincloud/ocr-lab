FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8080
# Single process on purpose: the simulated engine state (queue, batch, KV) lives in memory.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
