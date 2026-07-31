FROM node:22-bookworm-slim AS web_build

WORKDIR /web
COPY apps/web/package.json apps/web/pnpm-lock.yaml apps/web/pnpm-workspace.yaml ./
RUN corepack enable && pnpm install --frozen-lockfile
COPY apps/web/ ./
ENV NEXT_PUBLIC_API_URL=/api
RUN pnpm build && cp -r .next/static .next/standalone/.next/static

FROM python:3.12-slim

WORKDIR /app
COPY --from=web_build /usr/local/ /usr/local/
RUN apt-get update && apt-get install -y --no-install-recommends bash && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml README.md ./
COPY apps/api/ ./apps/api/
RUN pip install --no-cache-dir .
COPY --from=web_build /web/.next/standalone ./web
COPY pilot-seed/loa-piloto-educacao-render.zip /tmp/pilot.zip
RUN python -c "import zipfile; zipfile.ZipFile('/tmp/pilot.zip').extractall('/app/pilot-data')" && rm /tmp/pilot.zip
COPY scripts/start_render_free.sh ./scripts/start_render_free.sh
COPY scripts/render_proxy.mjs ./scripts/render_proxy.mjs
RUN chmod +x ./scripts/start_render_free.sh

ENV DATABASE_URL=sqlite:////app/pilot-data/loa.db
ENV STORAGE_DIR=/app/pilot-data
ENV SOURCE_DIR=/app/pilot-data/dados
ENV PILOT_EDUCATION_ONLY=true

CMD ["bash", "scripts/start_render_free.sh"]
