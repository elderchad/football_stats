FROM node:22-alpine AS web
WORKDIR /app
COPY web/package.json web/package-lock.json* ./
RUN npm install
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    STATIC_DIR=/srv/static \
    GAMES_CACHE_PATH=/tmp/nfl/games.csv \
    HISTORICAL_CACHE_PATH=/tmp/nfl/nfl_elo.csv \
    QB_STATS_CACHE_DIR=/tmp/nfl/qb_stats \
    NCAAF_CACHE_DIR=/tmp/nfl/ncaaf \
    NCAAF_HISTORY_CACHE_DIR=/tmp/nfl/ncaaf_history \
    PORT=8000

WORKDIR /srv

COPY api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY api/app ./app
COPY --from=web /app/dist ./static

RUN useradd --create-home --uid 10001 appuser \
 && mkdir -p /tmp/nfl \
 && chown -R appuser /tmp/nfl /srv
USER appuser

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
