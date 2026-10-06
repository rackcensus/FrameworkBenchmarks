FROM python:3.14@sha256:7e30bd51483a565ac6b2119af3f4cc179aba3ecd0b64d14cc9e64629df60d1f6

ADD ./ /django

WORKDIR /django

RUN pip install -r /django/requirements-gunicorn.txt

EXPOSE 8080

CMD gunicorn --pid=gunicorn.pid hello.wsgi:application -c gunicorn_conf.py --env DJANGO_DB=postgresql
