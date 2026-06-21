# kqxs_finetune

XSMB lottery analytics & prediction engine (Python + PostgreSQL).

## Stack

- FastAPI, psycopg3, APScheduler
- PostgreSQL 16 (Docker)
- Scrape: minhngoc.net.vn / xskt.com.vn

## Features

- Import & backfill XSMB history
- Statistical prediction engine (frequency, EWMA, gap, Markov, Bayesian, weekday, digit, ensemble)
- Walk-forward backtest & ensemble weight tuning
- Legacy-compatible `/kqxs/*` API

## Quick start

```bash
docker compose up -d
python -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env
.venv/bin/python run.py
```

## API

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Health check |
| `GET /predictions/next` | Predict next draw |
| `GET /predictions/weights` | Tuned ensemble weights |
| `POST /predictions/backtest` | Run backtest |
| `GET /analytics/stats` | DB stats |

## Docs

See [docs/SPEC-prediction-engine.md](docs/SPEC-prediction-engine.md).
