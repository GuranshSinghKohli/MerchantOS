# syntax=docker/dockerfile:1.7
FROM node:22-bookworm-slim AS deps
WORKDIR /repo
RUN corepack enable && corepack prepare pnpm@9.15.4 --activate
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/package.json
RUN pnpm install --frozen-lockfile --filter @merchantos/web...

FROM deps AS build
COPY apps/web apps/web
ARG API_UPSTREAM=http://127.0.0.1:8000
ENV NEXT_TELEMETRY_DISABLED=1 API_UPSTREAM=$API_UPSTREAM
RUN pnpm --filter @merchantos/web build

FROM node:22-bookworm-slim AS runtime
WORKDIR /app
RUN useradd --uid 65532 --create-home --shell /usr/sbin/nologin app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
COPY --from=build /repo/apps/web/public ./apps/web/public
COPY --from=build /repo/apps/web/.next/standalone ./
COPY --from=build /repo/apps/web/.next/static ./apps/web/.next/static
USER 65532:65532
EXPOSE 3000
HEALTHCHECK --interval=15s --timeout=3s --start-period=25s --retries=3 \
  CMD node -e "fetch('http://127.0.0.1:3000/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["node", "apps/web/server.js"]
