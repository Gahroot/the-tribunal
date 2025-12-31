# AI CRM Backend

AI-powered CRM backend with voice agents, SMS campaigns, and Cal.com integration.

## Features

- Multi-tenant workspace architecture
- AI voice agents via OpenAI Realtime
- SMS campaigns with AI takeover
- Cal.com appointment booking
- Telnyx telephony integration

## Setup

```bash
# Install dependencies
uv sync

# Start database
docker compose up -d

# Run migrations
uv run alembic upgrade head

# Start server
uv run uvicorn app.main:app --reload
```

## API Documentation

When running in debug mode, API docs are available at:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
