# Local Codex subscription integration

[中文](CODEX_LOGIN_CN.md)

This opt-in provider uses the official Codex CLI and a ChatGPT login on a trusted
local installation. It uses Codex account limits, not an OpenAI Platform API key.
Do not publish the bridge, use this account for untrusted tenants, or place login
files in this repository. See [official non-interactive documentation](https://learn.chatgpt.com/docs/non-interactive-mode).

## Setup

1. Install the standalone **Linux** Codex CLI on the Docker host. Version 0.164.0
   is the tested baseline; it must support `--ignore-user-config`, `--ignore-rules`,
   and `--ephemeral`. Resolve its native executable with `readlink -f $(command -v codex)`.
2. Build the updated backend with `docker compose build backend`. To reuse the
   installed dependencies from the matching published image, run
   `docker build -f backend_api_python/Dockerfile.local -t quantdinger-backend:local backend_api_python`
   instead. This copies application code, runtime scripts, and migrations together.
   After updating source, apply pending migrations with
   `docker compose run --rm --no-deps -e SKIP_AUTO_MIGRATE=false migration`
   before recreating application services.
3. Set these values in the ignored root `.env`:

   ```dotenv
   LLM_PROVIDER=codex
   CODEX_BRIDGE_URL=http://codex-bridge:8765
   CODEX_BRIDGE_TOKEN=<random internal secret of at least 32 characters>
   CODEX_CLI_BINARY=<absolute path to the native Linux Codex executable>
   CODEX_MODEL=
   CODEX_TIMEOUT=180
   ```

   Leave `CODEX_MODEL` empty to use the CLI default. No API key is needed. Never
   use the ChatGPT access token as `CODEX_BRIDGE_TOKEN`.
4. Initialize the private auth volume, then log in interactively:

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.codex.yml run --rm \
     --user 0 --cap-add CHOWN --entrypoint sh codex-bridge \
     -c 'mkdir -p /home/quantdinger/.codex && chown 10001:10001 /home/quantdinger/.codex'
   docker compose -f docker-compose.yml -f docker-compose.codex.yml run --rm \
     --entrypoint /usr/local/bin/codex codex-bridge login --device-auth
   ```

   Follow the official browser login. The auth volume persists refreshes. Keep
   it private, never print its `auth.json`, and never commit or share it.
5. Start the bridge and recreate the application processes:

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.codex.yml up -d \
     --no-deps --pull never codex-bridge backend celery-worker celery-beat
   ```

In **Settings → AI/LLM**, the provider now appears as **Codex**. Refresh an
already open settings page. Changing the dropdown does not install the CLI or
perform login; the bridge must already be configured.

## Start the complete local stack

After setup, run from the repository root:

```bash
./scripts/local-stack.sh up
./scripts/local-stack.sh check
./scripts/local-stack.sh status
```

This is one Compose project using `docker-compose.yml` and
`docker-compose.codex.yml`. The startup command explicitly includes PostgreSQL,
cache Redis, durable job Redis, Kafka, Codex bridge, backend, Celery worker,
Celery beat, trading worker, strategy dispatcher/evaluator, Kafka audit,
scheduler, frontend and mobile: fifteen persistent services. The Celery worker consumes the `jobs`, `ai` and `maintenance`
queues used by backtests and other finite tasks. Migration is a Compose
dependency and exits after successful execution, as do env-sync and kafka-init.
Strategy runtime workers restore deployments already marked running. Confirm
each saved broker account's paper/live setting before starting this full stack;
the strategy's `execution_mode=live` means broker execution and can use an Alpaca
paper account when that credential has `paper=true`.

`up` waits for the services and verifies the authenticated bridge health and
Celery queue response. It reuses existing containers and images (`--no-recreate`,
`--no-build`) and pulls only missing images (`--pull missing`); it is a restart entrypoint, not a code/image
upgrade. A bridge health success checks login configuration without generating
an LLM response or proving that the account has remaining allowance.

Persistent services have `restart: unless-stopped`. On this WSL installation,
the Docker system service is enabled, so existing containers restart when WSL
and Docker start. After an intentional `./scripts/local-stack.sh stop`, run
`up` to start them again. Restarting WSL interrupts running jobs; inspect their
durable status before retrying them.

The container entrypoint secures `.env` with mode `0600` under backend UID 10001,
including during migration. In WSL the script uses the distribution's root
management entry to run Compose with access to this file. On another Linux host,
use `sudo ./scripts/local-stack.sh up` if the operator cannot read it. The script
does not copy or print secrets or relax the entrypoint's permissions.
Database, application data and Codex login use the existing
named volumes. The script includes the complete strategy execution topology;
see the distributed-runtime deployment guide before upgrading or scaling it.

## Behavior

- The bridge has no host port, database connection, broker credentials, repository
  mount, or Docker socket. Only the standalone binary and the bridge script are
  mounted read-only; authentication uses a separate volume.
- Every request starts an ephemeral CLI run in an empty temporary directory.
  User/project configuration and rules are ignored. Shell, apps, browser,
  computer, multi-agent, and code-mode tools are disabled; the sandbox is read-only.
- API key variables and the bridge credential are excluded from the CLI
  environment. ChatGPT authentication is required; API-key login is rejected.
- Calls are serialized to avoid competing login refreshes. Failure does not
  trigger a paid provider fallback. Do not use this deployment for public traffic.
- Only text messages are supported. JSON responses use the CLI output schema;
  streaming callers receive one final text chunk, not live token deltas.
- Calls consume your Codex account allowance. Expiry, rate limits, and model
  availability follow that account. Re-run the device login if the session expires.

To disable, choose another configured provider and stop `codex-bridge`. This
does not delete login state; remove the auth volume only when deliberately
revoking this local integration.
