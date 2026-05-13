FROM python:3.13-slim

ARG CFO_SYNC_BUILD_BRANCH=""
ARG CFO_SYNC_BUILD_COMMIT=""

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    CFO_SYNC_BUILD_BRANCH=${CFO_SYNC_BUILD_BRANCH} \
    CFO_SYNC_BUILD_COMMIT=${CFO_SYNC_BUILD_COMMIT}

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src

