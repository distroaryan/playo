# Playto Payout Engine

This is a payment engine simulation using Django, DRF, PostgreSQL, Celery, and Redis.

## Setup Instructions

1. Ensure Docker and Docker Compose are installed on your machine.
2. The project comes with a `.env` file that has default credentials for local development.
3. Build and start the containers:
   ```bash
   docker-compose up --build -d
   ```
4. Verify all four containers (`postgres`, `redis`, `django`, `celery`) are running:
   ```bash
   docker-compose ps
   ```

## Local Development

To run commands inside the django container (e.g. migrations):
```bash
docker-compose exec django python manage.py migrate
```

## Environment Config

See `.env` for variables.
