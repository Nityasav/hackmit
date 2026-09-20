# The API is a long-lived process with a SQLite file on disk, so it needs a container host
# (Render, Railway, Fly) rather than Vercel's serverless functions, whose filesystem does not
# survive between invocations. Uploaded originals live in that file.
FROM python:3.12-slim

# rapidocr-onnxruntime pulls OpenCV, which links against libGL and glib at import time.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Dependencies resolve from the lockfile before the source is copied, so a code change does not
# reinstall the environment.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SCHOOLTRACE_DATA_DIR=/data

# Attach the host's volume at /data to keep uploads across restarts. Without one the directory
# still works and everything uploaded is lost on redeploy — survivable for a demo, but say it out
# loud. No VOLUME instruction here: Railway rejects a Dockerfile that declares one, because it
# mounts its own volume at the path you configure.
RUN mkdir -p /data

EXPOSE 8000

# Hosts inject the port they route to. One worker: SQLite holds the write lock per process.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
