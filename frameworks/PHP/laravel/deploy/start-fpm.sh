#!/bin/sh
set -e

if [ -n "$RC_WORKERS" ]; then
  children=$RC_WORKERS
  sed -i -e '/fastcgi_keep_conn on;/d' -e '/^ *keepalive [0-9]*;/d' /laravel/deploy/nginx.conf
elif [ "$(nproc)" = 2 ]; then
  children=512
else
  children=1024
fi
sed -i -e "s|^pm = .*|pm = static|" -e "s|^pm.max_children = .*|pm.max_children = $children|" /etc/php/8.5/fpm/php-fpm.conf

if [ -n "$RC_CPUS" ]; then
  sed -i "s|^worker_processes .*|worker_processes $RC_CPUS;|" /laravel/deploy/nginx.conf
fi

service php8.5-fpm start
exec nginx -c /laravel/deploy/nginx.conf
