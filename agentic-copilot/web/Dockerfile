# web/Dockerfile
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* pnpm-lock.yaml* yarn.lock* ./
# install deps (works with yarn/pnpm/npm)
RUN --mount=type=cache,target=/root/.npm \
    --mount=type=cache,target=/usr/local/share/.cache/yarn \
    --mount=type=cache,target=/root/.cache/pnpm \
    sh -lc ' \
      if [ -f yarn.lock ]; then yarn --frozen-lockfile; \
      elif [ -f pnpm-lock.yaml ]; then corepack enable && pnpm i --frozen-lockfile; \
      elif [ -f package-lock.json ]; then npm ci; \
      else npm install; fi \
    '

FROM node:20-alpine AS builder
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# ✅ Ensure 'marked' is present for Next build (dynamic import in pages/index.tsx)
RUN node -e "try{require.resolve('marked');process.exit(0)}catch(e){process.exit(1)}" \
 || (echo 'Installing missing dependency: marked' && npm install marked)

RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
# If you use Next standalone output, keep this:
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
EXPOSE 3000
CMD ["node", "server.js"]
