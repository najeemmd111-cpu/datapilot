# Run `python ml/train.py` against BigQuery first, so api/model.joblib exists.
FROM node:22-slim AS web
WORKDIR /web
COPY web/ .
RUN npm ci && npm run build

FROM python:3.13-slim
WORKDIR /app
COPY api/ .
RUN pip install --no-cache-dir -r requirements.txt -r requirements-cloud.txt && test -f model.joblib
COPY --from=web /web/dist/web/browser ./static
ENV DATA_BACKEND=bigquery
CMD exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}
