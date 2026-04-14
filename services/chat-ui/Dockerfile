# ============================================================
# Chat UI — Multi-stage Dockerfile (Next.js App Router)
# ============================================================
# Stage 1 (builder): Compiles TypeScript and builds .next/
# Stage 2 (runner):  Minimal image with only the standalone output
# OWASP A04: non-root user in production stage.
# ============================================================

# ── Stage 1: Build ───────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# NEXT_PUBLIC_ vars must be available at BUILD time (Next.js inlines them)
ARG NEXT_PUBLIC_API_URL=http://localhost:8003
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}

# Install deps with cache-friendly layer ordering
COPY package.json package-lock.json* ./
RUN npm ci

# Copy source and build
COPY . .
RUN mkdir -p public

# Generate standalone output (requires next.config setting)
RUN npm run build

# ── Stage 2: Production Runner ───────────────────────────────
FROM node:20-alpine AS runner

WORKDIR /app

# Security: non-root user (OWASP A04)
RUN addgroup --system --gid 1001 nodejs && \
    adduser  --system --uid 1001 --ingroup nodejs nextjs

# Copy only what the standalone server needs
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static     ./.next/static/
# public/ is optional (empty in this project), copy if it exists
RUN mkdir -p ./public
COPY --from=builder --chown=nextjs:nodejs /app/public ./public/

USER nextjs

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"
ENV NODE_ENV=production

# Health check — use 127.0.0.1 to avoid Alpine IPv6 resolution bug
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD wget -qO- http://127.0.0.1:3000/ > /dev/null || exit 1

CMD ["node", "server.js"]
