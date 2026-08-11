FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir flask

COPY server.py .

EXPOSE 8000

CMD ["python", "server.py"]
