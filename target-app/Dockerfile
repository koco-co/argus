ARG NODE_IMAGE=node:22.12.0-bookworm-slim@sha256:35531c52ce27b6575d69755c73e65d4468dba93a25644eed56dc12879cae9213
FROM ${NODE_IMAGE}

ARG DTC_SOURCE_URL
ARG DTC_COMMIT
ARG PNPM_VERSION

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git \
    && rm -rf /var/lib/apt/lists/* \
    && npm install --global "pnpm@${PNPM_VERSION}"

WORKDIR /server
RUN git init \
    && git remote add origin "${DTC_SOURCE_URL}" \
    && git fetch --depth=1 origin "${DTC_COMMIT}" \
    && git checkout --detach FETCH_HEAD \
    && test "$(git rev-parse HEAD)" = "${DTC_COMMIT}"

RUN pnpm install --frozen-lockfile

COPY overrides/medusa-config.ts /server/apps/backend/medusa-config.ts

# 服务端渲染走 Compose 内网；浏览器端仍使用可从宿主机访问的公开地址。
RUN sed -i \
    's/process.env.NEXT_PUBLIC_MEDUSA_BACKEND_URL/process.env.MEDUSA_INTERNAL_BACKEND_URL || process.env.NEXT_PUBLIC_MEDUSA_BACKEND_URL/g' \
    /server/apps/storefront/src/lib/config.ts \
    /server/apps/storefront/src/middleware.ts

WORKDIR /server/apps/backend
EXPOSE 9000 8000
