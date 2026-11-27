# One container: builds the React app, then serves it + the API from FastAPI.
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8
WORKDIR /app/backend
COPY backend/requirements.txt ./
# Some networks stall the large post-quantum TLS handshake of the image's OpenSSL 3.5 when talking
# to PyPI. Use classic key exchange for the package download only (the running app is unaffected).
RUN printf 'openssl_conf = i\n[i]\nssl_conf = s\n[s]\nsystem_default = d\n[d]\nGroups = X25519:P-256:P-384\n' > /tmp/pip-ssl.cnf \
 && OPENSSL_CONF=/tmp/pip-ssl.cnf pip install --no-cache-dir -r requirements.txt \
 && rm /tmp/pip-ssl.cnf
COPY backend/ ./
COPY --from=web /web/dist /app/frontend/dist
# Render / Cloud Run pass the port in $PORT
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
