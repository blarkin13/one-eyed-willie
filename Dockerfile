# Use Cloudflare's official connector image as the binary source (multi-architecture).
# This does not start a tunnel on its own; only an explicitly paired server does.
FROM cloudflare/cloudflared:2026.11.0 AS cloudflared

FROM python:3.12-slim
ARG TARGETARCH
LABEL org.opencontainers.image.source="https://github.com/blarkin13/one-eyed-willie" \
      org.opencontainers.image.title="Yarr Media server" \
      org.opencontainers.image.description="Self-hosted movie, TV and music server for Yarr Media" \
      org.opencontainers.image.url="https://yarr.media"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY --from=cloudflared /usr/local/bin/cloudflared /usr/local/bin/cloudflared
COPY requirements.txt .
# Intel VA-API drivers exist for x86 only; ARM builds use software encoding.
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ffmpeg tzdata \
      $( [ "${TARGETARCH:-amd64}" = "amd64" ] && echo intel-media-va-driver ) \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home --uid 10001 appuser
COPY server ./server
USER appuser
EXPOSE 8787
CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8787"]
