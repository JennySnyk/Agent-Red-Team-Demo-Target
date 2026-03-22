# Single-container SmartPal backend for red team demos.
# No frontend needed — snyk redteam hits /chat directly.
# JWT keys auto-generate on startup; GET /demo/info returns tokens + config.
#
# Usage:
#   make demo-scan API_KEY=your-api-key PROVIDER=google|openai|anthropic
#
# Manual:
#   docker build -f Dockerfile -t smartpal-demo ./smartpal/backend
#   docker run -p 4000:4000 -e SMARTPAL_PROVIDER=google -e SMARTPAL_API_KEY=your-key smartpal-demo

FROM python:3.13-slim

WORKDIR /smartpal

COPY pyproject.toml ./

RUN pip install .

COPY \
    ai.py \
    database.py \
    db_util.py \
    integrity.py \
    __init__.py \
    main.py \
    tools.py \
    utils.py \
    ./

EXPOSE 4000

ENV PYTHONUNBUFFERED=1

CMD ["python", "main.py"]
