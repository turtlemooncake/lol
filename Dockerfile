# Trading engine image. Long-running, supervised process (see docker-compose
# restart policy / the systemd unit in deploy/). Restarts are safe: every order
# carries a unique client_order_id the broker dedupes, so a replay after a crash
# never double-submits.
FROM python:3.10-slim

# Flush logs straight to the container's stdout (no Python buffering) so the
# supervisor and `docker logs` see them in real time; no stale .pyc on rebuild.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Install deps first so the layer caches across code-only changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Secrets come from the environment (.env via compose / EnvironmentFile via
# systemd), never baked into the image.
CMD ["python", "main.py"]
