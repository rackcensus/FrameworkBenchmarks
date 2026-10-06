FROM node:24-slim@sha256:d6aa754f16b3197301076f047b5def2f02ea1dbbc2ca920407d46d7ec7f87b20

COPY ./ ./

RUN npm ci
RUN npm run build && npm prune --omit=dev

ENV NODE_ENV production
ENV DATABASE_CONFIGURATION_PROFILE postgres
ENV FRAMEWORK express

EXPOSE 8080
CMD ["node", "dist/main"]
