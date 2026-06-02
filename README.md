# WOS Automation

Lightweight API and tooling for automating WOS tasks: giftcodes, players, redemptions, and scheduled jobs.

**Key areas:**
- API routers: giftcodes, players, redemptions, tasks, health
- Database integration (Supabase / DATABASE_URL)
- Captcha model + OCR-based solver utilities

**Quick links**
- API entrypoint: [app/main.py](app/main.py#L1)
- Config: [app/core/config.py](app/core/config.py#L1)
- Routers: [app/api/routers](app/api/routers)
- Error codes: [app/error_codes.json](app/error_codes.json#L1)

## Requirements
- Python 3.10+
- Install project dependencies from `pyproject.toml` (poetry) or via pip.

## Quickstart
1. Create and activate a virtualenv:

```bash
python -m venv .venv
source .venv/bin/activate
```

2. Install dependencies (editable install preferred):

```bash
# using pip
pip install -e .

# or with poetry
poetry install
```

3. Add runtime configuration: copy or create a `.env` file at the project root. The app loads env vars from `.env` via `app/core/config.py`.

Required environment variables (defined in [app/core/config.py](app/core/config.py#L1)):
- `SALT` — application salt string used for hashing
- `DATABASE_URL` — database/supabase connection URL
- `PRIORITY_ACCOUNT` — (string) account used for priority operations

Optional variables:
- `DEFAULT_PLAYER` — default player id
- `RENDER` — boolean flag to enable rendering features (default: False)
- `ERROR_CODES_FILE` — path to error codes JSON (default: `app/error_codes.json`)

4. Run the API server (development):

```bash
# using uvicorn
uvicorn app.main:app --reload

# or, if you use the `uv` CLI (project uses `uv` in some workflows):
uv run -m app.main --reload
```

The API will be available at `http://127.0.0.1:8000/`.

## Endpoints
Routers live in [app/api/routers](app/api/routers). Key endpoints include:
- Health: [app/api/routers/health.py](app/api/routers/health.py#L1)
- Giftcodes: [app/api/routers/giftcodes.py](app/api/routers/giftcodes.py#L1)
- Players: [app/api/routers/players.py](app/api/routers/players.py#L1)
- Redemptions: [app/api/routers/redemptions.py](app/api/routers/redemptions.py#L1)
- Tasks / jobs: [app/api/routers/tasks.py](app/api/routers/tasks.py#L1)

Explore the code in those files for specific routes and payloads.

## Development
- Tests: run `pytest` from the repo root. There are example notebooks under `tests/` and CSV fixtures used by tests.
- Interactive notebooks: `tests/*.ipynb` for exploratory work.

## Docker
There is a `Dockerfile` in the repo root. Build and run with:

```bash
docker build -t wos-automation .
docker run --env-file .env -p 8000:8000 wos-automation
```

## Notes
- Captcha model and metadata are stored in `model/` (`captcha_model.onnx`, `captcha_model_metadata.json`). See `utils/captcha_solver.py` for usage.
- Database helpers and Supabase utilities are under `app/db` and `db/`.

## Contributing
Open issues or PRs with focused changes. For large changes, open an issue first to discuss the design.

## License
This project is released under the MIT License — see [LICENSE](LICENSE) for details.

_Updated 2026-06-03_