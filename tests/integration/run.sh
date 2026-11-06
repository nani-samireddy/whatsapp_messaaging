#!/usr/bin/env bash
set -euo pipefail
mkdir -p /testbench/sites/assets /testbench/logs /testbench/config
ln -sfn /opt/frappe-test-env /testbench/env
printf 'frappe\nwhatsapp_messaging\n' > /testbench/sites/apps.txt
if [ ! -f /testbench/sites/common_site_config.json ]; then
  printf '{}\n' > /testbench/sites/common_site_config.json
fi
python_bin=/opt/frappe-test-env/bin/python
# Use built, read-only framework assets for the real PDF-rendering acceptance.
# No existing sites, site configuration or credentials are mounted.
"$python_bin" - <<'PY'
import json
from pathlib import Path
assets = Path('/testbench/sites/assets')
public = Path('/testbench/apps/frappe/frappe/public')
if not (assets / 'frappe').exists():
    (assets / 'frappe').symlink_to(public, target_is_directory=True)
manifest = {}
for bundle in ('print', 'print_format'):
    files = list((public / 'dist/css').glob(bundle + '.bundle.*.css'))
    if not files:
        raise RuntimeError('Build Frappe print assets before running the integration harness.')
    file = max(files, key=lambda path: path.stat().st_mtime)
    manifest[bundle + '.bundle.css'] = '/assets/frappe/dist/css/' + file.name
(assets / 'assets.json').write_text(json.dumps(manifest))
PY
"$python_bin" -c 'import frappe; assert frappe.__version__ == "16.52.0", frappe.__version__'
"$python_bin" -m frappe.utils.bench_helper frappe set-config -g db_host db
"$python_bin" -m frappe.utils.bench_helper frappe set-config -g redis_cache redis://redis:6379/0
"$python_bin" -m frappe.utils.bench_helper frappe set-config -g redis_queue redis://redis:6379/1
if [ ! -f /testbench/sites/whatsapp-test.localhost/site_config.json ]; then
  if [ -n "${WHATSAPP_TEST_BASELINE_PATH:-}" ]; then
    PYTHONPATH="/testbench/apps/frappe:$WHATSAPP_TEST_BASELINE_PATH" "$python_bin" -m frappe.utils.bench_helper frappe new-site whatsapp-test.localhost \
      --db-root-password integration-only-password --admin-password integration-only-admin \
      --mariadb-user-host-login-scope=% --install-app whatsapp_messaging
    PYTHONPATH="/testbench/apps/frappe:$WHATSAPP_TEST_BASELINE_PATH" "$python_bin" \
      /testbench/apps/whatsapp_messaging/tests/integration/seed_legacy.py
  else
    "$python_bin" -m frappe.utils.bench_helper frappe new-site whatsapp-test.localhost \
      --db-root-password integration-only-password --admin-password integration-only-admin \
      --mariadb-user-host-login-scope=% --install-app whatsapp_messaging
  fi
fi
"$python_bin" -m frappe.utils.bench_helper frappe --site whatsapp-test.localhost migrate
"$python_bin" /testbench/apps/whatsapp_messaging/tests/integration/check_plain_language.py
"$python_bin" /testbench/apps/whatsapp_messaging/tests/integration/check_site.py
"$python_bin" /testbench/apps/whatsapp_messaging/tests/integration/check_messaging.py
WHATSAPP_NAMING_TEST_SITE=whatsapp-test.localhost "$python_bin" /testbench/apps/whatsapp_messaging/tests/record_naming_integration.py
WHATSAPP_TOKEN_TEST_SITE=whatsapp-test.localhost "$python_bin" /testbench/apps/whatsapp_messaging/tests/access_token_length_integration.py

"$python_bin" /testbench/apps/whatsapp_messaging/tests/integration/check_template_configuration.py
"$python_bin" /testbench/apps/whatsapp_messaging/tests/integration/check_media_library.py
"$python_bin" /testbench/apps/whatsapp_messaging/tests/integration/check_media_cloud.py
"$python_bin" /testbench/apps/whatsapp_messaging/tests/integration/check_templates_campaigns.py

"$python_bin" /testbench/apps/whatsapp_messaging/tests/integration/check_flows.py

"$python_bin" /testbench/apps/whatsapp_messaging/tests/integration/check_production.py
WHATSAPP_DOCUMENT_TEST_SITE=whatsapp-test.localhost "$python_bin" /testbench/apps/whatsapp_messaging/tests/integration/check_document_delivery.py
