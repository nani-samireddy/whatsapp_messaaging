# Isolated Frappe integration tests

Requires Docker, the `frappe/bench` development image, a Frappe **16.52.0** source checkout, and a Linux Python 3.14 environment with its dependencies installed. The Python environment is mounted read-only; no existing sites, configuration or credentials are mounted.

```sh
export FRAPPE_FRAMEWORK_PATH=/path/to/frappe
export FRAPPE_PYTHON_ENV=/path/to/bench/env
docker compose -p whatsapp-security-tests -f tests/integration/compose.yaml up --abort-on-container-exit --exit-code-from test
```

This creates a separate database, Redis and bench volume. It publishes no ports and uses an internal-only network, preventing access to Meta and production services. Test fixtures use dummy credentials and addresses. Inspect failing output, then remove **only this test project** when finished:

```sh
docker compose -p whatsapp-security-tests -f tests/integration/compose.yaml down -v
```

Run from a fresh test volume to verify installation. Subsequent runs migrate and reuse only this isolated test site's schema. Tests use transactions or explicitly named fixtures and are not intended to run on a real site.

The harness runs the security and role checks, then inbox, outbox, webhook, media, schedule and campaign workflows. It also checks Desk app registration, HTTP authentication/permissions and a real RQ worker using mocked provider transport. Operational fixtures stay in the disposable site. The final naming checks cover readable series, title search and updates, unchanged historical IDs/keys/timestamps, and idempotent title backfill. Their fixture records and series counters roll back.

To verify a real upgrade, supply a clean checkout of the reviewed revision and use a different disposable project name:

```sh
export WHATSAPP_BASELINE_PATH=/path/to/clean/reviewed-app
docker compose -p whatsapp-security-upgrade -f tests/integration/compose.yaml -f tests/integration/upgrade.yaml up --abort-on-container-exit --exit-code-from test
```

The upgrade fixture installs the old schema first, inserts a dummy plaintext token, then runs the current migration and checks that the encrypted value survives and outbound requests stay off. Remove that test project's resources with the same files and project name plus `down -v`.

Long-token checks also verify complete encrypted save/reload/header round trips for 308- and 1,000-character fictional tokens, including preservation when editing another sender field. Fixtures roll back.
