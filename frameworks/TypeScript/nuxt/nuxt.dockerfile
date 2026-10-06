FROM node:24-slim@sha256:d6aa754f16b3197301076f047b5def2f02ea1dbbc2ca920407d46d7ec7f87b20 AS build

ENV NUXT_TELEMETRY_DISABLED="1"

WORKDIR /nuxt

COPY package.json package-lock.json ./
RUN npm ci

COPY ./ ./
RUN npm run build

FROM node:24-slim@sha256:d6aa754f16b3197301076f047b5def2f02ea1dbbc2ca920407d46d7ec7f87b20

ENV NODE_ENV="production"
ENV PORT="8080"
ENV HOST="0.0.0.0"

WORKDIR /nuxt

COPY --from=build /nuxt/.output ./.output

EXPOSE 8080

CMD ["sh", "-c", "NITRO_CLUSTER_WORKERS=${RC_WORKERS:-} exec node .output/server/index.mjs"]
