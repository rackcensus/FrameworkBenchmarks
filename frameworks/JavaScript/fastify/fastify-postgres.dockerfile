FROM node:24-slim@sha256:d6aa754f16b3197301076f047b5def2f02ea1dbbc2ca920407d46d7ec7f87b20

COPY ./ ./

RUN npm ci

ENV NODE_ENV production
ENV DATABASE postgres
ENV PG_HOST tfb-database
ENV PG_USER benchmarkdbuser
ENV PG_PSWD benchmarkdbpass
ENV PG_DBNAME hello_world

EXPOSE 8080

CMD ["node", "app.js"]
