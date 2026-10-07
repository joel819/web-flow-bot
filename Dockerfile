# Playwright image tag must match the playwright version in requirements.txt (1.56.0).
FROM mcr.microsoft.com/playwright/python:v1.56.0-noble

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
ENV PYTHONUNBUFFERED=1

# Default: run the bot. docker-compose overrides this for the demo site.
CMD ["python", "-m", "bot"]
