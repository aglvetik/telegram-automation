# Telegram Automation Service

Production-ready Telegram user-account automation service for Ubuntu VPS, built with `Telethon`, `httpx`, and environment-driven configuration.

## What changed

- Monolithic script replaced with a modular `app/` package.
- Telethon session storage moved to a dedicated configurable directory.
- Added a process lock file to prevent duplicate instances and session DB contention.
- Persisted per-chat `!start` / `!stop` state in SQLite so disabled chats stay disabled after restart.
- Replaced global mutable state with small dedicated classes for chat state, counters, history, and duplicate-event suppression.
- Added graceful async startup and shutdown with `asyncio.run(main())`, `async with TelegramClient(...)`, and `async with httpx.AsyncClient(...)`.
- Added configuration validation, structured logging, retries for outbound API calls, and minimal tests.

## Project layout

```text
app/
  config.py
  logging_config.py
  main.py
  runtime.py
  services/
  telegram/
  utils/
deploy/
  telegram-automation.service
tests/
main.py
pyproject.toml
requirements.txt
.env.example
```

## Setup

1. Create a virtual environment:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

3. Create `.env` from the example:

```bash
cp .env.example .env
chmod 600 .env
```

4. Fill in the required values:

- `TELEGRAM_API_ID`
- `TELEGRAM_API_HASH`
- `DEEPSEEK_API_KEY`
- `SYSTEM_PROMPT`

Everything else can stay at the defaults and be tuned later.
Keep values with spaces wrapped in quotes, exactly like in `.env.example`, so the same file works both for `python-dotenv` and for `systemd` `EnvironmentFile=...`.

## Manual first run and session notes

This service uses a real Telegram user session, so the very first login should be done manually in an interactive shell:

```bash
source .venv/bin/activate
python -m app.main
```

Telethon will create the session in `TELEGRAM_SESSION_DIR/TELEGRAM_SESSION_NAME.session`.
The chat enable/disable state is stored in `CHAT_STATE_DB_PATH`.
Use exactly one long-lived process per Telegram session. Do not keep a manual shell instance running after you enable the `systemd` service.

If you previously had `main_account.session` in the project root, the service automatically migrates legacy session files into the dedicated session directory on startup.

After the session exists and the account is authorized, you can run it through `systemd`.

## Runtime behavior

- Private chats are always eligible for auto-reply.
- Group chats reply only on mention, explicit mention string, reply-to-self, or when the configured message threshold is reached.
- `!stop` and `!start` are preserved as self-commands, but only your own outgoing messages can trigger them.
- `!stop` and `!start` are persisted per `chat_id` in SQLite. Chats missing from storage are enabled by default.
- Disabling a chat resets that chat's counter so it does not burst-reply immediately after re-enable.
- Short-term memory is stored per `(chat_id, user_id)` with TTL and message-count pruning.
- Dangerous messages return the fixed `DANGEROUS_REPLY` without calling the upstream LLM API. Matching is now token-boundary based, so unrelated substrings like `manuscript` no longer trip the `script` rule.
- Upstream LLM failures return `API_FALLBACK_REPLY`.

## Ubuntu VPS deployment

1. Upload or clone the repository:

```bash
git clone <your-repo-url> /opt/telegram-automation
cd /opt/telegram-automation
```

2. Create the venv and install dependencies:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

3. Create `.env`:

```bash
cp .env.example .env
chmod 600 .env
nano .env
```

4. Run manually once for authorization:

```bash
source .venv/bin/activate
python -m app.main
```

When that succeeds, stop the manual process before starting the `systemd` unit.

5. Install the systemd unit:

```bash
sudo cp deploy/telegram-automation.service /etc/systemd/system/telegram-automation.service
sudo systemctl daemon-reload
sudo systemctl enable telegram-automation
sudo systemctl start telegram-automation
```

6. Inspect logs:

```bash
sudo journalctl -u telegram-automation -f
```

## systemd notes

Update these fields in `deploy/telegram-automation.service` before enabling it:

- `User`
- `Group`
- `WorkingDirectory`
- `EnvironmentFile`
- `ExecStart`

The included example assumes the project lives in `/opt/telegram-automation` and the virtual environment is `.venv`.
`Restart=on-failure` is intentional: clean shutdowns from `systemctl stop` stay stopped, while unexpected crashes or disconnect exits are restarted automatically.

## Troubleshooting

### `sqlite3.OperationalError: database is locked`

This usually means two processes touched the same Telethon session database.

The refactor addresses that directly:

- the app uses a lock file tied to the session name
- the lock is acquired before any session migration or Telethon session access
- startup fails fast if another instance already owns the lock
- session files live in a dedicated directory instead of floating in the repo root

If you still see the error:

1. Stop all service instances.
2. Check for a second manually started process.
3. Verify `systemd` is only running one unit for this repo.
4. Make sure every deployment points to its own `TELEGRAM_SESSION_NAME` and `TELEGRAM_SESSION_DIR`.
5. Never run `python -m app.main` manually while the service is already running.

### Login fails under systemd

That is expected for a brand-new user account session. Run the app manually once in a shell, finish Telegram authorization, then restart the service under `systemd`.

### Duplicate or repeated replies

The service now keeps a short-lived in-memory guard for processed `(chat_id, message_id)` pairs to reduce duplicate handling after reconnects within the same running process. Running only one instance remains the main protection.

### Chat state database

The `!start` / `!stop` state is stored in SQLite at `CHAT_STATE_DB_PATH`.

Schema:

```sql
CREATE TABLE IF NOT EXISTS chat_states (
    chat_id INTEGER PRIMARY KEY,
    enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
    updated_at TEXT NOT NULL
);
```

The app creates this table automatically on startup. Unknown chats are enabled by default, matching the original behavior.

### Invalid `.env` under systemd

If the service fails immediately after boot, check `journalctl` first. A common cause is an invalid `.env` line. Keep any value with spaces quoted, especially:

- `DANGEROUS_REPLY`
- `API_FALLBACK_REPLY`
- `SYSTEM_PROMPT`

## Running tests

Install the dev extras if needed:

```bash
pip install ".[dev]"
pytest
```
