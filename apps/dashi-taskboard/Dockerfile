FROM node:22-alpine

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --registry=https://registry.npmmirror.com
COPY . .
RUN npm run build:web

ENV CODEX_TASKBOARD_HOST=0.0.0.0
ENV CODEX_TASKBOARD_PORT=47823
ENV CODEX_TASKBOARD_DATA_DIR=/data
EXPOSE 47823

CMD ["node", "server/index.mjs"]
