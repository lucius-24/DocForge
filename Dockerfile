FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    pandoc \
    curl \
    ca-certificates \
    fontconfig \
    fonts-noto-cjk \
    fonts-dejavu-core \
    && fc-cache -f \
    && rm -rf /var/lib/apt/lists/*

ARG AIDOC_SKIP_TYPST_DOWNLOAD=0
RUN if [ "$AIDOC_SKIP_TYPST_DOWNLOAD" != "1" ]; then \
      curl -fsSL -o /tmp/typst.tar.xz https://github.com/typst/typst/releases/latest/download/typst-x86_64-unknown-linux-musl.tar.xz \
      && mkdir -p /opt/typst \
      && tar -xJf /tmp/typst.tar.xz -C /opt/typst --strip-components=1 \
      && ln -s /opt/typst/typst /usr/local/bin/typst \
      && rm -f /tmp/typst.tar.xz ; \
    fi

COPY requirements.web.txt /app/requirements.web.txt
RUN pip install --no-cache-dir -r /app/requirements.web.txt

COPY . /app

ENV AIDOC_WEB_HOST=0.0.0.0
ENV AIDOC_WEB_PORT=8008

EXPOSE 8008

CMD ["uvicorn", "webapp.backend.server:app", "--host", "0.0.0.0", "--port", "8008"]
