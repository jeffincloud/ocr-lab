FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# KServe's LLMInferenceService template requires a non-root user.
USER 1000:1000
EXPOSE 8080
# Single process on purpose: the simulated engine state (queue, batch, KV) lives in memory.
# PORT and SSL_CERTFILE/SSL_KEYFILE let it stand in for vLLM inside an
# LLMInferenceService (port 8000, KServe's self-signed TLS).
ENV PORT=8080
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --no-access-log ${SSL_CERTFILE:+--ssl-certfile $SSL_CERTFILE --ssl-keyfile $SSL_KEYFILE}"]
