FROM node:24-slim@sha256:d6aa754f16b3197301076f047b5def2f02ea1dbbc2ca920407d46d7ec7f87b20

ENV NEXT_TELEMETRY_DISABLED="1"
ENV DATABASE_URL="postgres://benchmarkdbuser:benchmarkdbpass@tfb-database/hello_world"

ENV PORT="8080"
ENV HOSTNAME="0.0.0.0"

EXPOSE 8080

WORKDIR /nextjs

COPY package.json package-lock.json ./
RUN npm ci

COPY ./ ./
RUN npm run build \
 && cp -r public .next/standalone/ \
 && cp -r .next/static .next/standalone/.next/

ENV NODE_ENV="production"

CMD ["node", "cluster.js"]
