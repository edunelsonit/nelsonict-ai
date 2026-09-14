FROM python:3.12-slim-bookworm AS build
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 CMAKE_ARGS="-DGGML_NATIVE=OFF" CMAKE_BUILD_PARALLEL_LEVEL=2
RUN apt-get update && apt-get install -y --no-install-recommends build-essential cmake libgomp1 && rm -rf /var/lib/apt/lists/*
WORKDIR /build
COPY requirements.txt requirements-inference.txt requirements-ocr.txt ./
RUN pip wheel --wheel-dir=/wheels -r requirements.txt -r requirements-inference.txt -r requirements-ocr.txt

FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
    NELSON_DATA_DIR=/app/data NELSON_MODELS_DIR=/app/models
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 tesseract-ocr tesseract-ocr-eng && rm -rf /var/lib/apt/lists/*
COPY --from=build /wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links=/wheels /wheels/*.whl && rm -rf /wheels
ARG WITH_SEMANTIC=false
RUN if [ "$WITH_SEMANTIC" = "true" ]; then pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu && pip install --no-cache-dir "sentence-transformers>=5,<6"; fi
RUN useradd --create-home --uid 10001 nelson
WORKDIR /app
COPY app ./app
RUN mkdir -p /app/data /app/models /app/embeddings && chown -R nelson:nelson /app
USER nelson
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=4)"
CMD ["python","-m","uvicorn","app.main:app","--host","0.0.0.0","--port","8000","--workers","1"]
