FROM python:3.12-slim
WORKDIR /svc
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
# 127.0.0.1 only: reachable just by the Envoy sidecar sharing this network namespace, never directly.
CMD ["uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"]
