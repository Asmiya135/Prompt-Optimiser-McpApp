FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY optimizer ./optimizer
COPY llm ./llm
COPY server ./server

# Run as a non-root user.
RUN useradd --create-home appuser
USER appuser

EXPOSE 8080
CMD ["python", "-m", "server.app"]
