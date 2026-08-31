# syntax=docker/dockerfile:1.7
FROM caddy:2.10-alpine
COPY Caddyfile /etc/caddy/Caddyfile
RUN apk add --no-cache wget \
  && mkdir -p /data /config && chown -R 65532:65532 /data /config /etc/caddy
USER 65532:65532
EXPOSE 80 443
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
  CMD wget -qO- http://127.0.0.1/health || exit 1
