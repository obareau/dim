# D.I.M — Dockerfile
# Multi-stage build: lean runtime image for the web interface.
#
# Build:
#   docker build -t dim:latest .
#
# Run:
#   docker run -p 5001:5001 dim:latest
#   docker run -p 5001:5001 -v $(pwd)/my_project.json:/project.json dim:latest /project.json
#
# With docker-compose:
#   docker compose up

# ── Stage 1: builder ──────────────────────────────────────────────────────────
FROM python:3.13-slim AS builder

WORKDIR /build

# Install build deps
RUN pip install --upgrade pip wheel

# Copy only what pip needs to resolve dependencies
COPY requirements.txt pyproject.toml ./

# Install runtime dependencies into a prefix
RUN pip install --prefix=/install \
    flask>=3.0 \
    flask-socketio>=5.0 \
    python-osc>=1.8 \
    zeroconf>=0.80 \
    "python-socketio[client]>=5.0"

# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM python:3.13-slim AS runtime

LABEL org.opencontainers.image.title="D.I.M — Dawless Is More"
LABEL org.opencontainers.image.description="Non-linear performance sequencer"
LABEL org.opencontainers.image.authors="Olivier Bareau <olivier.bareau@gmail.com>"
LABEL org.opencontainers.image.source="https://github.com/obareau/dim"
LABEL org.opencontainers.image.licenses="MIT"

# Copy installed packages from builder
COPY --from=builder /install /usr/local

WORKDIR /app

# Copy application source
COPY core/         core/
COPY network/      network/
COPY adapters/     adapters/
COPY dim_pkg/      dim_pkg/
COPY formats/      formats/
COPY run_web.py    .

# Expose web port
EXPOSE 5001

# Default: start web server on all interfaces
ENV PYTHONPATH=/app \
    DIM_HOST=0.0.0.0 \
    DIM_PORT=5001

ENTRYPOINT ["python", "-m", "dim_pkg"]
CMD ["--host", "0.0.0.0", "--port", "5001"]
