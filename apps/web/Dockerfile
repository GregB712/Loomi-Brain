FROM node:24-bookworm-slim

WORKDIR /app

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml .npmrc ./
COPY patches patches
COPY apps/web/package.json apps/web/package.json
COPY packages/contracts/package.json packages/contracts/package.json
COPY packages/ui/package.json packages/ui/package.json
RUN corepack enable && corepack pnpm install --frozen-lockfile

COPY tsconfig.base.json tsconfig.base.json
COPY apps/web apps/web
COPY packages/contracts packages/contracts
COPY packages/ui packages/ui

EXPOSE 3000

CMD ["corepack", "pnpm", "--filter", "@loomi/web", "exec", "next", "dev", "--hostname", "0.0.0.0", "--port", "3000"]
