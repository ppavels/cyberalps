FROM node:22-bookworm-slim AS frontend
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund
COPY index.html vite.config.js ./
COPY src ./src
COPY public ./public
COPY scripts/prerender.mjs ./scripts/prerender.mjs
RUN npm run build

FROM python:3.12-slim-bookworm
ARG REVISION=development
LABEL org.opencontainers.image.source="https://github.com/ppavels/cyberalps"
LABEL org.opencontainers.image.revision=$REVISION
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATA_DIR=/data PORT=3002 CYBERALPS_REVISION=$REVISION
WORKDIR /app
RUN groupadd --gid 10001 cyberalps && useradd --uid 10001 --gid 10001 --no-create-home cyberalps && mkdir /data && chown 10001:10001 /data
COPY --from=frontend /build/dist ./dist
COPY app ./app
USER 10001:10001
EXPOSE 3002
HEALTHCHECK --interval=20s --timeout=5s --start-period=10s --retries=3 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:3002/api/health', timeout=3)"]
CMD ["python", "-m", "app.server"]
