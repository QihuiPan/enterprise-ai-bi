FROM node:22-alpine AS builder

WORKDIR /app
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN corepack enable \
    && corepack prepare pnpm@11.19.0 --activate \
    && pnpm install --frozen-lockfile
COPY frontend/ .
ARG VITE_API_URL=""
ARG VITE_API_KEY_HEADER=X-API-Key
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_API_KEY_HEADER=$VITE_API_KEY_HEADER
RUN pnpm build

FROM nginx:1.31.5-alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
