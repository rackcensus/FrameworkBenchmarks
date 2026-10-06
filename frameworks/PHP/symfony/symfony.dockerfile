FROM ubuntu:24.04@sha256:534baea6a22c03a63003dbc8dbe78fe34bc0d7e595d9a9dc9834884ff530eb55

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update -yqq && apt-get install -yqq software-properties-common > /dev/null
RUN LC_ALL=C.UTF-8 add-apt-repository -y ppa:ondrej/php > /dev/null && \
    apt-get upgrade -yqq > /dev/null

RUN apt-get install -yqq nginx git unzip curl \
    php8.5-bcmath php8.5-cli php8.5-fpm php8.5-pgsql  \
    php8.5-mbstring php8.5-xml php8.5-curl php8.5-intl > /dev/null

# Use Jemalloc for optimize
RUN apt install libjemalloc2
ENV LD_PRELOAD=libjemalloc.so.2

COPY --from=composer/composer:2-bin@sha256:696bfbbb82d8ab6ad3672c505bedd659e3815fd1c03cb5ef65ef7ee07a083fa6 --link /composer /usr/local/bin/composer

COPY --link deploy/conf/* /etc/php/8.5/fpm/

WORKDIR /symfony
COPY --link . .

RUN composer install --optimize-autoloader --classmap-authoritative --no-dev --no-scripts --quiet
RUN cp deploy/postgresql/.env . && composer dump-env prod && bin/console cache:clear

RUN echo "opcache.preload=/symfony/var/cache/prod/App_KernelProdContainer.preload.php" >> /etc/php/8.5/fpm/php.ini

EXPOSE 8080

# Uncomment next line for Laravel console error logging to be viewable in docker logs
# RUN echo "catch_workers_output = yes" >> /etc/php/8.5/fpm/php-fpm.conf

RUN mkdir -p /run/php
CMD ["/symfony/deploy/start-fpm.sh"]