"""Offline diagnostic probes of the reviewed source. No Frappe site or network used.

These isolate source functions with fake dependencies; they are evidence of function
behavior, not full Frappe/Meta integration tests or a proposed application test suite.
"""
import ast
import json
import re
import subprocess
from pathlib import Path
from types import SimpleNamespace as NS

ROOT = Path(__file__).resolve().parents[3]
REVISION = "d55395fe92f576287c3a1a1778e135bf3e21f9d5"


def functions(path, names, env):
    source = subprocess.run(["git", "show", f"{REVISION}:whatsapp_messaging/{path}"], cwd=ROOT, check=True, capture_output=True, text=True).stdout
    tree = ast.parse(source)
    tree.body = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    for node in tree.body:
        node.decorator_list = []
    exec(compile(tree, str(ROOT / path), "exec"), env)
    return env


results = []


def record(name, observed):
    assert observed, name
    results.append({"probe": name, "confirmed": True})


logs = []
frappe = NS(log_error=lambda *a, **kw: logs.append(a), throw=lambda s: (_ for _ in ()).throw(ValueError(s)))
env = functions("utils/__init__.py", ["format_phone_number", "datetime_to_cron_format"],
                {"frappe": frappe, "datetime": __import__("datetime").datetime})
record("phone normalization retains spaces and parentheses",
       env["format_phone_number"]("+91 (987) 654-3210") == "91 (987) 6543210")
record("one-shot cron drops year and seconds",
       env["datetime_to_cron_format"]("2026-10-18 09:45:59") == "45 9 18 10 *")

row = NS(static_recipient="Example recipient")
seen = []
frappe.get_value = lambda dt, key, f: seen.append(key)
env = functions("controller.py", ["get_template_recipients"],
                {"frappe": frappe, "format_phone_number": env["format_phone_number"]})
template = NS(phone_number_field_name="mobile", get=lambda key, default: [row])
env["get_template_recipients"](template, NS(get=lambda field: "+919876543210"))
record("static recipient lookup receives child object instead of linked name", seen == [row])

body = "{{phone_number_id.access_token}}"
sentinel = "OFFLINE-DUMMY-NOT-A-CREDENTIAL"
frappe.get_value = lambda *args: body
frappe.get_all = lambda *args, **kw: [{"fieldname": "phone_number_id", "options": "WhatsApp Phone Number ID"}]
frappe.get_doc = lambda *args: NS(access_token=sentinel)
env = functions("controller.py", ["parse_message", "process_placeholder"], {"frappe": frappe, "re": re})
rendered = env["parse_message"](NS(name="demo", doctype="WhatsApp Message Template", phone_number_id="demo"), NS())
record("renderer interpolates linked account token without authorization", rendered == sentinel)

outbound = []
env = functions("controller.py", ["process_template_and_send"], {
    "frappe": frappe, "parse_message": lambda *a: "Hello", "get_template_recipients": lambda **kw: ["919876543210"],
    "get_cloud_api_url": lambda **kw: "OFFLINE", "get_headers": lambda **kw: {},
    "send_bulk_messages": lambda **kw: outbound.append(kw)})
env["process_template_and_send"](NS(), NS(disable=1, media=None, phone_number_id="demo", template_type="interactive"))
record("disabled interactive template still builds free-text send", len(outbound) == 1 and outbound[0]["payload"]["type"] == "text")

saved = []
job = NS(stopped=False, save=lambda: saved.append("job"))
template = NS(template_event="Scheduled", schedule_job_type_link="demo", schedule_status="Pending", save=lambda: saved.append("template"))
frappe.get_doc = lambda dt, name: template if dt == "WhatsApp Message Template" else job
env = functions("controller.py", ["process_scheduled_messages"], {"frappe": frappe, "process_template_query": lambda t: None})
env["process_scheduled_messages"]("demo")
record("scheduler marks completion without any per-recipient result", job.stopped and template.schedule_status == "Completed")

status_logs = []
env = functions("utils/message_controller.py", ["send_message"], {
    "frappe": frappe, "json": json,
    "make_post_request": lambda *a, **kw: {"messages": [{"id": "wamid.offline"}]},
    "log_wa_message": lambda *a: status_logs.append(a)})
env["send_message"]({"type": "text", "text": {"body": "Hello"}})
record("HTTP acceptance is logged Sent and provider ID is not passed to logger", status_logs[0][1:] == ("Sent", ""))

filters_seen = []
env = functions("utils/__init__.py", ["doc_matches_filters"], {"evaluate_filters": lambda d, f: filters_seen.append(f)})
env["doc_matches_filters"]({}, '{"filters": [["status", "=", "Open"]]}')
record("document-event filter evaluator receives unparsed JSON string", isinstance(filters_seen[0], str))

Path(__file__).with_name("review-checks-results.json").write_text(json.dumps({
    "scope": "Offline isolated source functions with stubbed dependencies; no network or site operations",
    "revision": "d55395fe92f576287c3a1a1778e135bf3e21f9d5", "results": results
}, indent=2) + "\n")
print(f"PASS: {len(results)} offline review probes; confirmed behaviors recorded without real credentials or sends")
