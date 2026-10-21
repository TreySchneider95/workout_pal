FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    WORKOUT_DATA_DIR=/data \
    WORKOUT_SEED_PATH=/seed/home_gym_workout_with_images.zip

WORKDIR /app

COPY requirements.txt requirements-dev.txt ./
# Dev requirements are tiny and let you run the test suite inside the container.
RUN pip install -r requirements-dev.txt

COPY . .

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')" || exit 1

ENTRYPOINT ["./docker-entrypoint.sh"]
