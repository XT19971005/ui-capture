FROM ubuntu:24.04@sha256:68ee22004a9109b44973313b02ff7b1de250f1de0f5ecb628d73f579aaff33ac AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends python3 python3-venv nodejs npm ca-certificates libglib2.0-0t64 libgl1 fonts-noto-cjk fonts-liberation tini && python3 -m venv /opt/venv && rm -rf /var/lib/apt/lists/*
ENV PATH=/opt/venv/bin:/app/node_modules/.bin:$PATH
WORKDIR /app
COPY deploy/requirements.lock /app/deploy/requirements.lock
RUN pip install --require-hashes -r deploy/requirements.lock
COPY package.json package-lock.json /app/
RUN npm ci --omit=dev && npm cache clean --force
RUN groupadd -g 10001 shijie && useradd -u 10001 -g shijie -m shijie && mkdir /data && chown shijie:shijie /data
FROM runtime AS app
COPY --chown=10001:10001 . /app
ENV SHIJIE_CONFIG=/run/secrets/config.toml SHIJIE_PRODUCTION=1
USER 10001:10001
ENTRYPOINT ["/usr/bin/tini", "-g", "--"]
CMD ["gunicorn", "config.wsgi:application", "--bind=0.0.0.0:8093", "--workers=2", "--threads=2", "--timeout=120", "--max-requests=1000", "--access-logfile=-", "--access-logformat=%(h)s %(m)s %(U)s %(s)s %(L)s"]
