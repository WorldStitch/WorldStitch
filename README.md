# WorldStitch

A creative worldbuilding platform for novels, games, films, TTRPGs, and any fiction that needs a living world. Manage characters, notes, maps, timelines, factions, locations, and AI-assisted lore — all in one place.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React (Vite) |
| Backend | FastAPI (Python 3.11+) |
| Database | SQLite (local / dev), PostgreSQL (hosted) |
| AI | OpenAI API |

---

## Setup

### Prerequisites

- Python 3.11+
- Node.js 18+
- Git

### First-time setup

```bash
git clone https://github.com/sike-ward/WorldStitch.git
cd WorldStitch

# Python backend
python -m venv .venv
.venv\Scripts\Activate.ps1    # Windows PowerShell
pip install -r requirements.txt

# Copy and fill in environment variables
cp .env.example .env
# Edit .env — set JWT_SECRET and ADMIN_PASSWORD at minimum
```

### Environment variables

| Variable | Description |
|----------|-------------|
| `JWT_SECRET` | Random hex string — `python -c "import secrets; print(secrets.token_hex(32))"` |
| `ADMIN_EMAIL` | Email for the first admin account |
| `ADMIN_PASSWORD` | Password for the first admin account |
| `OPENAI_API_KEY` | Optional — enables AI features |
| `APP_ENV` | `development` (default), `production`, or `test` |
| `LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING` (default: `INFO`) |

All other settings live in `WorldStitch/config/settings.json`.

---

## Running in development

```bash
# Terminal 1 — Python backend (from project root)
python -m uvicorn server.app:app --host 127.0.0.1 --port 8741 --reload

# Terminal 2 — React frontend
cd frontend
npm install
npm run dev
```

Or use the convenience launcher:

```bat
Launch_WorldStitch.bat
```

---

## Role system

| Role | Access |
|------|--------|
| `owner` | Full control — manage users, billing, instance settings |
| `admin` | Manage users and groups within the instance |
| `moderator` | Moderate content within a group |
| `tester` | Access to pre-release features |
| `user` | Standard access |

---

## Project structure

```
WorldStitch/
├── server/           # FastAPI routes and business logic
├── frontend/         # React (Vite) UI
├── migrations/       # Alembic database migrations
├── WorldStitch/      # Python layer (storage, managers, models)
│   ├── auth/         # Auth manager, session manager, permission checker
│   ├── config/       # Config loader
│   ├── context/      # AppContext — central service locator
│   ├── managers/     # Business logic (one manager per entity type)
│   ├── models/       # Pydantic data models
│   ├── storage/      # StorageBackend interface, SQLiteBackend, HybridStorage
│   └── tests/        # pytest test suite
├── .env.example      # Environment variable template
├── requirements.txt  # Python dependencies
└── TECH_DEBT.md      # Known issues and deferred work
```

---

## Development

```bash
# Lint + format
ruff check .
ruff format .

# Tests
pytest WorldStitch/tests/

# Type check
mypy WorldStitch/models/ WorldStitch/managers/ WorldStitch/storage/
```

---

## Marketing site

`landing/index.html` is the self-contained marketing site for [worldstitch.app](https://worldstitch.app). It is a single HTML file with all CSS inlined — no build step required. Serve it as a static file or open it directly in a browser.

---

## License

Private project — all rights reserved.
