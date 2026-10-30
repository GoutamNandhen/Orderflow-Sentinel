FROM node:22-bookworm-slim AS frontend
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY shared ./shared
COPY shop-frontend ./shop-frontend
COPY console-frontend ./console-frontend
RUN node node_modules/typescript/bin/tsc --noEmit -p shop-frontend/tsconfig.json \
    && node node_modules/typescript/bin/tsc --noEmit -p console-frontend/tsconfig.json \
    && cd shop-frontend && node ../node_modules/vite/bin/vite.js build --base=/shop/ \
    && cd ../console-frontend && node ../node_modules/vite/bin/vite.js build --base=/console/

FROM python:3.11-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*
COPY backend/requirements-cloud.txt ./backend/requirements-cloud.txt
RUN pip install --no-cache-dir -r backend/requirements-cloud.txt
COPY backend ./backend
COPY --from=frontend /build/shop-frontend/dist ./shop-frontend/dist
COPY --from=frontend /build/console-frontend/dist ./console-frontend/dist
RUN useradd --uid 10001 --create-home appuser && chown -R appuser:appuser /app
USER appuser
EXPOSE 10000
CMD ["sh", "-c", "exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-10000} --workers 1 --no-access-log --log-level warning"]
