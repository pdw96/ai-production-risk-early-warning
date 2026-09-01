# 의존성 설치 → 빌드 → 실행을 분리해 최종 이미지에서 개발 의존성과 소스를 제외한다.
FROM node:22-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-slim AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# next.config.ts의 rewrites()는 빌드 시점에 .next/routes-manifest.json으로 구워진다.
# 런타임 env로는 프록시 대상이 바뀌지 않으므로 반드시 빌드 인자로 넣어야 한다.
#   bridge 네트워크(compose.yaml)          → http://backend:8000
#   host 네트워크(compose.codespaces.yaml) → http://127.0.0.1:8000
ARG API_INTERNAL_BASE_URL=http://backend:8000
ENV API_INTERNAL_BASE_URL=${API_INTERNAL_BASE_URL}
RUN npm run build

FROM node:22-slim AS runner
WORKDIR /app
ENV NODE_ENV=production \
    HOSTNAME=0.0.0.0 \
    PORT=3000
# output: "standalone" 빌드는 실행에 필요한 node_modules만 추려 server.js와 함께 내보낸다.
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
EXPOSE 3000
CMD ["node", "server.js"]
