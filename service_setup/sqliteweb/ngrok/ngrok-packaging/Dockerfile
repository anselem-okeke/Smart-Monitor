FROM python:3.12-alpine

# Install sqlite-web
RUN pip install --no-cache-dir sqlite-web==0.6.7

# Fetch ngrok
ARG NGROK_ARCH=linux-amd64
RUN wget -qO /tmp/ngrok.zip https://bin.equinox.io/c/4VmDzA7iaHb/ngrok-stable-${NGROK_ARCH}.zip \
    && unzip /tmp/ngrok.zip -d /usr/local/bin \
    && rm /tmp/ngrok.zip

# Create app user and dirs
RUN adduser -D app && mkdir -p /data /etc/ngrok /var/log/smartmon \
     && chown -R app:app /data /etc/ngrok /var/log/smartmon \

USER app

# Defaults (override at runtime)
ENV SQLITE_DATABASE=smart_factory_monitor.db
ENV NGROK_AUTHTOKEN=""
ENV NGROK_ADDR=127.0.0.1:8080
ENV NGROK_BASIC_AUTH=""
ENV PORT=8080

COPY entrypoint.sh /entrypoint.sh
EXPOSE 8080
ENTRYPOINT ["/entrypoint.sh"]

