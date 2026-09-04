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
# O pacote instalado busca o vocabulário em /usr/local/lib/config.
COPY config/ /usr/local/lib/config/
COPY --from=web_build /web/.next/standalone ./web
COPY pilot-seed/loa-homologada-render.zip /tmp/loa-homologada.zip
RUN python -c "import zipfile; zipfile.ZipFile('/tmp/loa-homologada.zip').extractall('/app/loa-data')" && rm /tmp/loa-homologada.zip
COPY scripts/start_render_free.sh ./scripts/start_render_free.sh
COPY scripts/render_proxy.mjs ./scripts/render_proxy.mjs
RUN chmod +x ./scripts/start_render_free.sh

ENV DATABASE_URL=sqlite:////app/loa-data/loa.db
ENV STORAGE_DIR=/app/loa-data
ENV SOURCE_DIR=/app/loa-data/dados
ENV PILOT_EDUCATION_ONLY=false

CMD ["bash", "scripts/start_render_free.sh"]
