# API + worker image for the Reputation Console backend.
FROM python:3.12-slim

WORKDIR /app

# System deps kept minimal; psycopg[binary] ships its own libpq.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Default: serve the API. The worker service overrides this command (see docker-compose).
CMD ["uvicorn", "rep_engine.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
