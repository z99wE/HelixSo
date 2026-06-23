FROM python:3.9-slim

WORKDIR /app

COPY . .

EXPOSE 7860

ENTRYPOINT ["python", "-m", "http.server", "7860"]
