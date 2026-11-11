FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN apt-get update && apt-get install -y --no-install-recommends build-essential cmake && rm -rf /var/lib/apt/lists/*
ENV CMAKE_BUILD_PARALLEL_LEVEL=2
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home findme && mkdir /data && chown findme:findme /data
COPY requirements-drive.txt .
RUN pip install --no-cache-dir -r requirements-drive.txt
ARG FACE_BACKEND=dlib
COPY requirements-arcface.txt .
RUN if [ "$FACE_BACKEND" = arcface ]; then pip install --no-cache-dir -r requirements-arcface.txt; fi
COPY app ./app
COPY scripts ./scripts
RUN python scripts/download_model.py
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--no-proxy-headers"]
