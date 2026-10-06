FROM ruby:4.0@sha256:08325a579fcef06b1d53aab2d0c9f9dad8b12a454b7d65fda6e8fbb695299856

RUN apt-get update -yqq && apt-get install -yqq --no-install-recommends redis-server

EXPOSE 8080
WORKDIR /rails

ENV RUBY_YJIT_ENABLE=1
ENV RUBY_MN_THREADS=1

# Use Jemalloc
RUN apt-get update && \
    apt-get install -y --no-install-recommends libjemalloc2
ENV LD_PRELOAD=libjemalloc.so.2

COPY ./Gemfile* /rails/

ENV BUNDLE_FORCE_RUBY_PLATFORM=true
ENV BUNDLE_WITH=postgresql:puma
RUN bundle install --jobs=8

COPY . /rails/

ENV RAILS_MAX_THREADS=5
ENV RAILS_ENV=production_postgresql
ENV PORT=8080
ENV REDIS_URL=redis://localhost:6379/0
CMD export WEB_CONCURRENCY=${RC_WORKERS:-$(($(nproc)*5/4))} && \
    export RAILS_MAX_THREADS=${RC_THREADS:-$RAILS_MAX_THREADS} && \
    if [ "$RC_ENABLE_CACHE" = "1" ]; then service redis-server start; fi && \
    bin/rails server
