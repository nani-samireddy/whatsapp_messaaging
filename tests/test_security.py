"""Local regression tests; transport and Frappe boundaries are fake, never networked.

Run: python3 -m unittest discover -s tests -v
Full DocType lifecycle/permission tests still require a disposable Frappe site.
"""

import ast
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

from whatsapp_messaging.template_security import (
	TemplateSecurityError, parse_allowed_fields, render_message,
)

ROOT = Path(__file__).resolve().parents[1] / "whatsapp_messaging"


def load_function(path, name, globals_):
	"""Isolate a real entry point so its permission boundary can be tested locally."""
	tree = ast.parse((ROOT / path).read_text())
	tree.body = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name]
	for node in tree.body:
		node.decorator_list = []
	exec(compile(tree, str(ROOT / path), "exec"), globals_)
	return globals_[name]


def throw(message, exception=ValueError):
	raise exception(message)


class TestTemplateSecurity(unittest.TestCase):
	def test_approved_source_and_template_label(self):
		value = Mock(return_value="Asha")
		self.assertEqual(render_message("Hello {{template_doctype.patient_name}} / {{self.template_name}}",
			value, {"template_name": "Reminder"}, {"patient_name"}), "Hello Asha / Reminder")
		value.assert_called_once_with("patient_name")

	def test_linked_account_and_unapproved_fields_never_reach_resolver(self):
		resolver = Mock()
		for placeholder in ("phone_number_id.access_token", "self.access_token", "template_doctype.salary",
			"template_doctype.password", "template_doctype.patient.name", "__dict__", "self.__dict__"):
			with self.subTest(placeholder=placeholder), self.assertRaises(TemplateSecurityError):
				render_message("{{" + placeholder + "}}", resolver, {}, {"patient_name", "password"})
		resolver.assert_not_called()

	def test_invalid_or_missing_values_fail_closed(self):
		for text in ("", "  ", "Hello {{template_doctype.patient_name}", "{{}}", "{{unknown}}"):
			with self.subTest(text=text), self.assertRaises(TemplateSecurityError):
				render_message(text, lambda name: "Asha", {}, {"patient_name"})
		for value in (None, ""):
			with self.subTest(value=value), self.assertRaises(TemplateSecurityError):
				render_message("{{template_doctype.patient_name}}", lambda name: value, {}, {"patient_name"})

	def test_zero_and_false_are_valid_values(self):
		self.assertEqual(render_message("{{template_doctype.balance}}", lambda name: 0, {}, {"balance"}), "0")
		self.assertEqual(render_message("{{template_doctype.enabled}}", lambda name: False, {}, {"enabled"}), "False")

	def test_static_placeholders_use_only_the_explicit_static_resolver(self):
		value = Mock(return_value="Riverbend Hospital")
		self.assertEqual(render_message("{{static.hospital_settings.hospital_name}}", Mock(), {}, set(), static_value=value), "Riverbend Hospital")
		value.assert_called_once_with("hospital_settings", "hospital_name")
		for token in ("static.hospital_settings.access_token", "static.hospital_settings.name.extra", "other.hospital_settings.name"):
			value.reset_mock()
			with self.assertRaises(TemplateSecurityError):
				render_message("{{"+token+"}}", Mock(), {}, set(), static_value=value)
			value.assert_not_called()
		with self.assertRaises(TemplateSecurityError):
			render_message("{{static.hospital_settings.hospital_name}}", Mock(), {}, set())

	def test_allowlist_validation(self):
		self.assertEqual(parse_allowed_fields('["patient_name", "appointment_date"]'),
			frozenset({"patient_name", "appointment_date"}))
		for value in ('{}', '"patient_name"', '[1]', '["access_token"]', '["patient.name"]', 'broken'):
			with self.subTest(value=value), self.assertRaises(TemplateSecurityError):
				parse_allowed_fields(value)

	def test_renderer_checks_source_record_and_field_permission(self):
		field = NS(fieldtype="Data", hidden=0, print_hide=0)
		doc = NS(meta=NS(get_field=Mock(return_value=field)),
			check_permission=Mock(), has_permlevel_access_to=Mock(return_value=False), get=Mock(return_value="private"))
		template = NS(template_doctype="Patient", message_preview="{{template_doctype.patient_name}}", get=lambda k: '["patient_name"]' if k == "allowed_source_fields" else None)
		render = load_function("controller.py", "parse_message", {
			"parse_allowed_fields": parse_allowed_fields, "get_allowed_source_fields": lambda source: frozenset({"patient_name"}), "render_message": render_message,
			"SAFE_SOURCE_TYPES": {"Data"}, "SENSITIVE_FIELD": __import__("re").compile("token"),
			"TemplateSecurityError": TemplateSecurityError, "static_value": Mock()})
		with self.assertRaises(TemplateSecurityError):
			render(template, doc)
		doc.check_permission.assert_called_once_with("read")
		doc.get.assert_not_called()


class TestSendBoundaries(unittest.TestCase):
	def setUp(self):
		self.frappe = NS(session=NS(user="agent"), get_roles=Mock(return_value=["Whatsapp Editor"]),
			PermissionError=PermissionError, throw=throw, has_permission=Mock(return_value=True), get_doc=Mock(),
			whitelist=lambda **kw: lambda fn: fn)
		spec = importlib.util.spec_from_file_location("isolated_send_security", ROOT / "send_security.py")
		self.policy = importlib.util.module_from_spec(spec)
		with patch.dict("sys.modules", {"frappe": self.frappe}):
			spec.loader.exec_module(self.policy)
		self.template = NS(disable=0, is_single=0, template_event="Custom", template_doctype="Patient",
			phone_number_id="Support", query_filters=None, check_permission=Mock())

	def test_unrelated_role_and_guest_are_rejected(self):
		self.frappe.get_roles.return_value = ["Website User"]
		with self.assertRaises(PermissionError): self.policy.require_send_role()
		self.frappe.session.user = "Guest"
		self.frappe.get_roles.return_value = ["System Manager"]
		with self.assertRaises(PermissionError): self.policy.require_send_role()

	def test_editor_cannot_bulk_send(self):
		with self.assertRaises(PermissionError): self.policy.require_send_role(bulk=True)

	def test_invalid_template_modes_are_rejected(self):
		for attr, value in (("disable", 1), ("template_doctype", "Payroll"), ("template_event", "Scheduled"), ("is_single", 1)):
			with self.subTest(attr=attr):
				original = getattr(self.template, attr); setattr(self.template, attr, value)
				with self.assertRaises(ValueError): self.policy.check_template_policy(self.template, "Patient")
				setattr(self.template, attr, original)

	def test_template_and_account_are_checked(self):
		account = Mock(); self.frappe.get_doc.return_value = account
		self.policy.check_manual_template(self.template, "Patient")
		self.template.check_permission.assert_called_once_with("read")
		account.check_permission.assert_called_once_with("read")

	def test_endpoint_rejects_role_before_document_reads_or_send(self):
		send = Mock(); role = Mock(side_effect=PermissionError("denied"))
		entry = load_function("controller.py", "wm_handle_on_custom_trigger", {
			"frappe": self.frappe, "require_send_role": role, "process_template_and_send": send})
		with self.assertRaises(PermissionError): entry("demo", "Patient", "demo")
		self.frappe.get_doc.assert_not_called(); send.assert_not_called()

	def test_endpoint_checks_record_before_send(self):
		doc = Mock(); doc.check_permission.side_effect = PermissionError("denied")
		self.frappe.get_doc.side_effect = [doc]
		send = Mock()
		entry = load_function("controller.py", "wm_handle_on_custom_trigger", {
			"frappe": self.frappe, "require_send_role": Mock(), "check_manual_template": Mock(),
			"process_template_and_send": send})
		with patch.dict("sys.modules", {"whatsapp_messaging.messaging.campaigns": NS(load=Mock(return_value=self.template))}):
			with self.assertRaises(PermissionError): entry("demo", "Patient", "demo")
		doc.check_permission.assert_called_once_with("read")
		send.assert_not_called()

	def test_disabled_dispatch_does_not_render_or_send(self):
		self.template.disable = 1
		render = Mock(); send = Mock()
		entry = load_function("controller.py", "process_template_and_send", {
			"frappe": self.frappe, "parse_message": render, "send_bulk_messages": send})
		entry(NS(doctype="Patient"), self.template)
		render.assert_not_called(); send.assert_not_called()

	def test_bulk_action_creates_preview_without_synchronous_transport(self):
		import sys
		preview = Mock(return_value={"run": "preview"})
		module = NS(preview_campaign=preview)
		self.template.name = "rule"
		entry = load_function("controller.py", "process_template_query", {"frappe": self.frappe})
		with patch.dict(sys.modules, {"whatsapp_messaging.messaging.automation": module}):
			self.assertEqual(entry(self.template, "Patient", permission_checked=True), {"run": "preview"})
		preview.assert_called_once_with("rule")
		self.frappe.get_doc.assert_not_called()

	def test_static_recipient_uses_link_value(self):
		self.frappe.get_doc = Mock(return_value=NS(phone_number="+91 9876543210", check_permission=Mock()))
		self.template.phone_number_field_name = None
		self.template.get = lambda *a: [NS(static_recipient="Asha")]
		entry = load_function("controller.py", "get_template_recipients", {
			"frappe": self.frappe, "format_phone_number": lambda x: x})
		self.assertEqual(entry(self.template, Mock()), ["919876543210"])
		self.frappe.get_doc.assert_called_once_with("Static Recipient", "Asha")

	def test_json_filter_envelope_is_decoded(self):
		evaluate = Mock(return_value=True)
		entry = load_function("utils/__init__.py", "doc_matches_filters", {"json": json, "evaluate_filters": evaluate})
		doc = {"doctype": "Patient", "status": "Open"}
		self.assertTrue(entry(doc, '{"doctype":"Patient","filters":[["status","=","Open"]]}'))
		evaluate.assert_called_once_with(doc, [["status", "=", "Open"]])

	def test_untrusted_graph_host_is_rejected(self):
		entry = load_function("utils/config.py", "get_cloud_api_url", {
			"frappe": self.frappe, "urlsplit": __import__("urllib.parse", fromlist=["urlsplit"]).urlsplit})
		for url in ("http://graph.facebook.com", "https://example.com", "https://graph.facebook.com@example.com", "https://graph.facebook.com/path"):
			with self.subTest(url=url):
				self.frappe.get_doc.side_effect = [NS(whatsapp_api_url=url, whatsapp_api_version="v26.0"), NS(phone_number_id="123")]
				with self.assertRaises(ValueError): entry("Support")

	def test_graph_resource_segments_cannot_override_the_endpoint(self):
		entry = load_function("utils/config.py", "get_cloud_api_url", {
			"frappe": self.frappe, "re": __import__("re"),
			"urlsplit": __import__("urllib.parse", fromlist=["urlsplit"]).urlsplit})
		for version, phone in (("v26.0/other", "123"), ("v26.0", "123/messages?x=y")):
			with self.subTest(version=version, phone=phone):
				self.frappe.get_doc.side_effect = [NS(whatsapp_api_url="https://graph.facebook.com", whatsapp_api_version=version), NS(phone_number_id=phone)]
				with self.assertRaises(ValueError): entry("Support")
		self.frappe.get_doc.side_effect = [NS(whatsapp_api_url="https://graph.facebook.com/", whatsapp_api_version="v26.0"), NS(phone_number_id="123")]
		self.assertEqual(entry("Support"), "https://graph.facebook.com/v26.0/123/messages")

	def test_authorization_header_uses_the_password_store(self):
		account = NS(access_token="********", get_password=Mock(return_value="dummy-test-token"))
		self.frappe.get_doc.return_value = account
		entry = load_function("utils/config.py", "get_headers", {"frappe": self.frappe})
		self.assertEqual(entry("Support")["authorization"], "Bearer dummy-test-token")
		account.get_password.assert_called_once_with("access_token", raise_exception=False)

	def test_disabled_gate_does_not_consult_a_cached_value(self):
		self.frappe.db = NS(get_single_value=Mock(return_value=0))
		with self.assertRaises(ValueError): self.policy.require_outbound_enabled()
		self.frappe.db.get_single_value.assert_called_once_with("WhatsApp Settings", "enable_outbound_messages", cache=False)

	def test_existing_app_roles_supply_their_capabilities(self):
		self.frappe.db = NS(get_single_value=Mock(return_value=0))
		for role, bulk, credentials in (("Whatsapp Editor", False, False), ("Whatsapp Admin", True, False), ("System Manager", True, True)):
			with self.subTest(role=role):
				self.frappe.get_roles.return_value = [role]
				access = self.policy.get_messaging_access()
				self.assertTrue(access["can_send"])
				self.assertEqual(access["can_bulk_send"], bulk)
				self.assertEqual(access["can_manage_credentials"], credentials)
				self.assertFalse(access["outbound_enabled"])

	def test_unrelated_user_cannot_read_messaging_capabilities(self):
		self.frappe.db = NS(get_single_value=Mock())
		self.frappe.get_roles.return_value = ["Website User"]
		with self.assertRaises(PermissionError): self.policy.get_messaging_access()
		self.frappe.db.get_single_value.assert_not_called()


class TestRecipientPhoneFields(unittest.TestCase):
	def picker(self, fields, permitted=None):
		meta = NS(fields=fields, get_permitted_fieldnames=lambda **kw: permitted or [f.fieldname for f in fields])
		return load_function("utils/__init__.py", "get_input_fields", {
			"json": json, "frappe": NS(throw=throw), "get_meta": lambda doctype: meta,
			"_check_metadata_permission": Mock()})

	def test_phone_picker_supports_both_frappe_phone_formats(self):
		fields = [NS(fieldname="mobile", fieldtype="Phone", hidden=0),
			NS(fieldname="patient_phone_number", fieldtype="Data", options="Phone", hidden=0),
			NS(fieldname="description", fieldtype="Data", options="", hidden=0)]
		picker = self.picker(fields)
		self.assertEqual(picker("Patient", '["Phone"]'), ["mobile", "patient_phone_number"])
		# The other source-field picker passes an empty optional filter over HTTP.
		self.assertEqual(picker("Patient", ''), ["mobile", "patient_phone_number", "description"])

	def test_phone_picker_excludes_hidden_sensitive_and_unreadable_fields(self):
		fields = [NS(fieldname=name, fieldtype="Data", options="Phone", hidden=hidden)
			for name, hidden in (("mobile", 0), ("hidden_phone", 1), ("secret_phone", 0), ("private_phone", 0))]
		self.assertEqual(self.picker(fields, ["mobile", "hidden_phone", "secret_phone"])("Patient", ["Phone"]), ["mobile"])

	def test_recipient_resolution_accepts_data_phone_and_preserves_guards(self):
		field = NS(fieldname="patient_phone_number", fieldtype="Data", options="Phone", hidden=0)
		doc = NS(meta=NS(get_field=lambda name: field), get=lambda name: "+1 (202) 555-0100",
			has_permlevel_access_to=lambda *a, **kw: True)
		template = NS(phone_number_field_name=field.fieldname, get=lambda name: [])
		entry = load_function("controller.py", "get_template_recipients", {"frappe": NS(throw=throw, PermissionError=PermissionError)})
		self.assertEqual(entry(template, doc), ["12025550100"])
		for bad in (NS(fieldname="patient_phone_number", fieldtype="Data", options="", hidden=0),
			NS(fieldname="secret_phone", fieldtype="Data", options="Phone", hidden=0),
			NS(fieldname="patient_phone_number", fieldtype="Data", options="Phone", hidden=1)):
			doc.meta.get_field = lambda name, bad=bad: bad
			with self.assertRaises(PermissionError): entry(template, doc)
		doc.meta.get_field = lambda name: field
		doc.has_permlevel_access_to = lambda *a, **kw: False
		with self.assertRaises(PermissionError): entry(template, doc)


if __name__ == "__main__":
	unittest.main()
