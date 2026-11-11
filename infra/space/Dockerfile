# Hugging Face Spaces image. deploy_space.py copies this to the Space's root.
FROM node:22-slim AS web
WORKDIR /web
COPY web/ .
RUN npm ci && npm run build

FROM python:3.13-slim
# Spaces run as user 1000.
RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:$PATH" DATA_BACKEND=local PORT=7860
WORKDIR /home/user/app
COPY --chown=user api/requirements.txt api/requirements-cloud.txt ./api/
RUN pip install --no-cache-dir --user -r api/requirements.txt -r api/requirements-cloud.txt
COPY --chown=user api/ ./api/
COPY --chown=user data/local/ ./data/local/
COPY --chown=user ml/train.py ./ml/train.py
# Train inside the image so the model matches its scikit-learn version.
RUN python ml/train.py
COPY --chown=user --from=web /web/dist/web/browser ./api/static
WORKDIR /home/user/app/api
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
