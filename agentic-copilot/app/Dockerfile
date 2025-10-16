# syntax=docker/dockerfile:1.7
FROM python:3.11-slim AS app

# Keep your envs (and add a couple safe speed/stability ones)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_INPUT=1

WORKDIR /app

# Install only what you actually need to build wheels.
# If git/build-essential aren't required by your deps, remove them to speed it up further.
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential git \
  && rm -rf /var/lib/apt/lists/*

# 1) Cache Python deps: this layer only busts when requirements.txt changes
COPY requirements.txt /tmp/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r /tmp/requirements.txt

# 2) Copy your source last so code edits don’t invalidate the deps layer
COPY src /app/src

# Keep your exposed port the same
EXPOSE 8080

# Keep the same default command (compose can override if needed)
CMD ["python", "-m", "src.main"]
