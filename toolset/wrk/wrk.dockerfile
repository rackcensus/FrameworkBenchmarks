FROM ubuntu:24.04@sha256:534baea6a22c03a63003dbc8dbe78fe34bc0d7e595d9a9dc9834884ff530eb55

ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get install --no-install-recommends -qqUy curl wrk > /dev/null

# Required scripts for benchmarking
COPY concurrency.sh pipeline.lua pipeline.sh query.sh ./
