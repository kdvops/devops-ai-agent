FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends git kubernetes-client && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py agent.py persistence.py app_queue.py worker.py index.html ./
COPY integrations ./integrations
RUN useradd --create-home --uid 10001 agent && mkdir /workspace && chown agent:agent /workspace
USER 10001
ENV WORKSPACE_ROOT=/workspace KUBERNETES_READ_ONLY=true ALLOWED_NAMESPACES=*
EXPOSE 8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
