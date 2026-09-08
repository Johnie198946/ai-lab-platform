FROM node:22.23.2-alpine3.24@sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32 AS build

WORKDIR /app
COPY package.json package-lock.json ./
RUN apk upgrade --no-cache \
    && npm ci --registry=https://registry.npmmirror.com
COPY . .
RUN npm run build:web \
    && npm prune --omit=dev

FROM node:22.23.2-alpine3.24@sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32

RUN apk upgrade --no-cache \
    && mkdir /data \
    && chown node:node /data \
    && rm -rf /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/corepack \
    && rm -f /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack \
      /usr/local/bin/yarn /usr/local/bin/yarnpkg /usr/local/bin/pnpm /usr/local/bin/pnpx

WORKDIR /app
COPY --from=build --chown=node:node /app /app

ENV CODEX_TASKBOARD_HOST=0.0.0.0
ENV CODEX_TASKBOARD_PORT=47823
ENV CODEX_TASKBOARD_DATA_DIR=/data
EXPOSE 47823

USER node

HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=6 \
    CMD ["wget", "-q", "-O", "-", "http://127.0.0.1:47823/api/meta"]

CMD ["node", "server/index.mjs"]
