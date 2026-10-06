FROM python:3.14@sha256:7e30bd51483a565ac6b2119af3f4cc179aba3ecd0b64d14cc9e64629df60d1f6

WORKDIR /fastapi

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip3 install cython==3.2.3

COPY . ./

RUN pip3 install -r requirements-gunicorn.txt

EXPOSE 8080

CMD gunicorn app:app -k uvicorn.workers.UvicornWorker -c fastapi_conf.py
