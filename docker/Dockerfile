FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY fbot ./fbot
COPY scripts ./scripts
COPY config ./config
ARG GIT_SHA=unknown
ENV FBOT_GIT_SHA=$GIT_SHA PYTHONUNBUFFERED=1 TZ=UTC
RUN useradd -r -u 10001 fbot && mkdir -p /app/data && chown -R fbot /app/data
USER fbot
ENTRYPOINT ["python", "-m", "fbot.recorder.main"]
CMD ["--config", "config/recorder.toml"]
