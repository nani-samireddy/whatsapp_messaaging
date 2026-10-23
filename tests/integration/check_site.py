"""Real Frappe schema, encryption, permissions, transactions and HTTP tests.

Only run using the isolated Compose project. Every token and person is a fixture.
"""

import os
import subprocess
import time
import unittest
from unittest.mock import patch

import frappe
import requests

SITE = "whatsapp-test.localhost"
ACCOUNT = "WM Integration Account"
TEMPLATE = "WM Integration Template"
EDITOR = "wm-editor@example.invalid"
SUPERVISOR = "wm-supervisor@example.invalid"
UNRELATED = "wm-unrelated@example.invalid"
DUMMY_TOKEN = "integration-only-dummy-token"
SOURCE = None
CONVERSATION_RECIPIENT = "WM integration peer"
CONVERSATION = None


def connect():
	frappe.init(site=SITE, sites_path="/testbench/sites")
	frappe.connect()
	frappe.set_user("Administrator")


def seed():
	global SOURCE, CONVERSATION
	assert frappe.local.site == SITE and frappe.conf.db_host == "db", "Isolated test site required"
	frappe.db.set_single_value("WhatsApp Settings", "enable_outbound_messages", 0)
	frappe.db.set_single_value("WhatsApp Settings", "whatsapp_api_url", "https://graph.facebook.com")
	frappe.db.set_single_value("WhatsApp Settings", "whatsapp_api_version", "v26.0")
	for email, roles in ((EDITOR, ["Whatsapp Editor"]), (SUPERVISOR, ["Whatsapp Admin"]), (UNRELATED, [])):
		if not frappe.db.exists("User", email):
			frappe.get_doc({"doctype": "User", "email": email, "first_name": "Integration",
				"send_welcome_email": 0, "user_type": "System User", "roles": [{"role": role} for role in roles],
				"new_password": "integration-only-user-password"}).insert()
	account = frappe.get_doc("WhatsApp Phone Number ID", ACCOUNT) if frappe.db.exists("WhatsApp Phone Number ID", ACCOUNT) else frappe.new_doc("WhatsApp Phone Number ID")
	account.update({"label": ACCOUNT, "phone_number_id": "1234567890", "access_token": DUMMY_TOKEN})
	account.save()
	if not frappe.db.exists("WhatsApp Template Field Policy", "ToDo"):
		frappe.get_doc({"doctype":"WhatsApp Template Field Policy", "source_doctype":"ToDo", "allowed_fields":'["status"]'}).insert()
	else:
		policy = frappe.get_doc("WhatsApp Template Field Policy", "ToDo")
		policy.allowed_fields = '["status"]'
		policy.save()
	template = frappe.get_doc("WhatsApp Message Template", TEMPLATE) if frappe.db.exists("WhatsApp Message Template", TEMPLATE) else frappe.new_doc("WhatsApp Message Template")
	template.update({"template_name": TEMPLATE, "template_doctype": "ToDo", "template_event": "Custom",
		"is_single": 0, "disable": 0, "phone_number_id": ACCOUNT,
		"message_preview": "Hello {{template_doctype.status}}", "allowed_source_fields": '["status"]'})
	template.save()
	SOURCE = frappe.db.exists("ToDo", {"description": "WM integration source"})
	if not SOURCE:
		SOURCE = frappe.get_doc({"doctype": "ToDo", "description": "WM integration source", "status": "Open", "owner": EDITOR}).insert().name
	frappe.db.set_value("ToDo", SOURCE, "allocated_to", EDITOR)
	CONVERSATION = frappe.db.get_value("WhatsApp Conversation", {"recipient": CONVERSATION_RECIPIENT}, "name")
	if not CONVERSATION:
		CONVERSATION = frappe.get_doc({"doctype": "WhatsApp Conversation", "recipient": CONVERSATION_RECIPIENT,
			"conversations": [{"from": "Frappe", "status": "Sent", "message_type": "text", "message": "Fixture history"}]}).insert().name
	frappe.db.commit()


class TestDatabaseSecurity(unittest.TestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint("security_case")
		self.posts = patch("whatsapp_messaging.utils.message_controller.make_post_request", side_effect=AssertionError("Transport forbidden"))
		self.transport = self.posts.start()

	def tearDown(self):
		self.posts.stop()
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="security_case")
		frappe.clear_document_cache("WhatsApp Settings", "WhatsApp Settings")

	def test_password_is_encrypted_and_row_is_masked(self):
		account = frappe.get_doc("WhatsApp Phone Number ID", ACCOUNT)
		self.assertEqual(account.get_password("access_token"), DUMMY_TOKEN)
		self.assertNotEqual(frappe.db.get_value(account.doctype, account.name, "access_token"), DUMMY_TOKEN)
		self.assertNotIn(DUMMY_TOKEN, frappe.as_json(account.as_dict()))
		self.assertEqual(account.meta.get_field("access_token").fieldtype, "Password")
		self.assertEqual(account.meta.get_field("access_token").permlevel, 1)

	def test_legacy_migration_is_idempotent(self):
		from frappe.utils.password import get_decrypted_password, remove_encrypted_password
		from whatsapp_messaging.patches.v1_0.encrypt_access_tokens import execute
		remove_encrypted_password("WhatsApp Phone Number ID", ACCOUNT, "access_token")
		frappe.db.set_value("WhatsApp Phone Number ID", ACCOUNT, "access_token", DUMMY_TOKEN)
		execute()
		execute()
		self.assertEqual(get_decrypted_password("WhatsApp Phone Number ID", ACCOUNT, "access_token"), DUMMY_TOKEN)
		self.assertEqual(frappe.db.get_value("WhatsApp Phone Number ID", ACCOUNT, "access_token"), "********")

	def test_missing_encrypted_value_is_not_replaced_by_mask(self):
		from frappe.utils.password import remove_encrypted_password
		from whatsapp_messaging.patches.v1_0.encrypt_access_tokens import execute
		remove_encrypted_password("WhatsApp Phone Number ID", ACCOUNT, "access_token")
		with self.assertRaises(frappe.ValidationError): execute()

	def test_headers_use_decrypted_value(self):
		from whatsapp_messaging.utils.config import get_headers
		self.assertEqual(get_headers(ACCOUNT)["authorization"], "Bearer " + DUMMY_TOKEN)

	def test_migration_uses_the_callers_transaction(self):
		from frappe.utils.password import get_decrypted_password, remove_encrypted_password
		from whatsapp_messaging.patches.v1_0.encrypt_access_tokens import execute
		remove_encrypted_password("WhatsApp Phone Number ID", ACCOUNT, "access_token")
		frappe.db.set_value("WhatsApp Phone Number ID", ACCOUNT, "access_token", DUMMY_TOKEN)
		frappe.db.savepoint("before_migration")
		execute()
		frappe.db.rollback(save_point="before_migration")
		self.assertEqual(frappe.db.get_value("WhatsApp Phone Number ID", ACCOUNT, "access_token"), DUMMY_TOKEN)
		self.assertIsNone(get_decrypted_password("WhatsApp Phone Number ID", ACCOUNT, "access_token", raise_exception=False))

	def test_default_gate_stops_send_before_transport(self):
		from whatsapp_messaging.utils.message_controller import send_message
		with self.assertRaises(frappe.ValidationError): send_message({"type": "text"}, url="https://graph.facebook.com")
		self.transport.assert_not_called()

	def test_default_gate_stops_upload_before_file_access(self):
		from whatsapp_messaging.utils.media_controller import upload_media_to_whatsapp
		with patch("requests.sessions.Session.request") as transport:
			with self.assertRaises(frappe.ValidationError): upload_media_to_whatsapp("unused", frappe._dict())
			transport.assert_not_called()

	def test_gate_does_not_reuse_an_enabled_value_from_cache(self):
		from whatsapp_messaging.send_security import require_outbound_enabled
		frappe.db.value_cache["WhatsApp Settings"]["enable_outbound_messages"] = 1
		with self.assertRaises(frappe.ValidationError): require_outbound_enabled()

	def test_template_rendering_checks_real_field_permissions(self):
		from whatsapp_messaging.controller import parse_message
		template = frappe.get_doc("WhatsApp Message Template", TEMPLATE)
		doc = frappe.get_doc({"doctype": "ToDo", "description": "fixture content", "status": "Open"})
		self.assertEqual(parse_message(template, doc), "Hello Open")

	def test_account_placeholder_cannot_be_rendered(self):
		from whatsapp_messaging.controller import parse_message
		from whatsapp_messaging.template_security import TemplateSecurityError
		template = frappe.get_doc("WhatsApp Message Template", TEMPLATE)
		template.message_preview = "{{phone_number_id.access_token}}"
		with self.assertRaises(TemplateSecurityError): parse_message(template, frappe.get_doc({"doctype": "ToDo", "description": "fixture"}))

	def test_existing_roles_can_authorize_a_manual_send(self):
		from whatsapp_messaging.send_security import check_manual_template
		for user in (EDITOR, SUPERVISOR):
			frappe.set_user(user)
			check_manual_template(frappe.get_doc("WhatsApp Message Template", TEMPLATE), "ToDo")
		self.transport.assert_not_called()

	def test_editor_cannot_authorize_bulk_send(self):
		from whatsapp_messaging.send_security import check_manual_template
		frappe.set_user(EDITOR)
		template = frappe.get_doc("WhatsApp Message Template", TEMPLATE)
		template.is_single = 1
		with self.assertRaises(frappe.PermissionError): check_manual_template(template, "ToDo", bulk=True)

	def test_supervisor_can_authorize_bulk_send(self):
		from whatsapp_messaging.send_security import check_manual_template
		frappe.set_user(SUPERVISOR)
		template = frappe.get_doc("WhatsApp Message Template", TEMPLATE)
		template.is_single = 1
		check_manual_template(template, "ToDo", bulk=True)
		self.transport.assert_not_called()

	def test_app_role_does_not_grant_access_to_an_unreadable_source_type(self):
		from whatsapp_messaging.send_security import check_manual_template
		frappe.set_user(EDITOR)
		template = frappe.get_doc("WhatsApp Message Template", TEMPLATE)
		template.template_doctype = "Email Account"
		with self.assertRaises(frappe.PermissionError): check_manual_template(template, "Email Account")
		self.transport.assert_not_called()

	def test_whatsapp_supervision_does_not_override_source_record_access(self):
		from whatsapp_messaging.controller import wm_handle_on_custom_trigger
		frappe.set_user(SUPERVISOR)
		with self.assertRaises(frappe.PermissionError): wm_handle_on_custom_trigger(TEMPLATE, "ToDo", SOURCE)
		self.transport.assert_not_called()

	def test_app_roles_read_history_but_cannot_rewrite_it(self):
		for user in (EDITOR, SUPERVISOR):
			frappe.set_user(user)
			doc = frappe.get_doc("WhatsApp Conversation", CONVERSATION)
			doc.check_permission("read")
			doc.conversations[0].message = "Changed history"
			with self.assertRaises(frappe.PermissionError): doc.save()
			with self.assertRaises(frappe.PermissionError): frappe.delete_doc(doc.doctype, doc.name)

	def test_unrelated_user_cannot_read_history(self):
		frappe.set_user(UNRELATED)
		with self.assertRaises(frappe.PermissionError):
			frappe.get_doc("WhatsApp Conversation", CONVERSATION).check_permission("read")

	def test_unrelated_user_is_rejected_before_send(self):
		from whatsapp_messaging.controller import wm_handle_on_custom_trigger
		frappe.set_user(UNRELATED)
		with self.assertRaises(frappe.PermissionError): wm_handle_on_custom_trigger(TEMPLATE, "ToDo", "does-not-exist")
		self.transport.assert_not_called()

	def test_filter_json_matches_real_frappe_evaluator(self):
		from whatsapp_messaging.utils import doc_matches_filters
		doc = frappe.get_doc({"doctype": "ToDo", "description": "fixture", "status": "Open"})
		self.assertTrue(doc_matches_filters(doc, '{"filters":[["status","=","Open"]]}'))
		self.assertFalse(doc_matches_filters(doc, '{"filters":[["status","=","Closed"]]}'))

	def test_approved_field_configuration_is_protected(self):
		template = frappe.get_doc("WhatsApp Message Template", TEMPLATE)
		frappe.set_user(EDITOR)
		template.allowed_source_fields = '["status","allocated_to"]'
		template.save()
		self.assertEqual(frappe.db.get_value(template.doctype, template.name, "allowed_source_fields"), '["status"]')

	def test_disabled_automation_does_not_publish_event_jobs(self):
		from whatsapp_messaging.controller import handle_doc_events
		with patch("frappe.enqueue") as enqueue:
			handle_doc_events(frappe.get_doc({"doctype": "ToDo", "description": "fixture"}), ["Create"])
			enqueue.assert_not_called()


class TestTransactions(unittest.TestCase):
	def test_job_is_published_only_after_commit_and_not_after_rollback(self):
		from frappe.utils.background_jobs import get_queue
		frappe.db.rollback()
		queue = get_queue("default")
		before = queue.count
		frappe.enqueue("frappe.utils.now", enqueue_after_commit=True)
		self.assertEqual(queue.count, before)
		frappe.db.rollback()
		self.assertEqual(queue.count, before)
		frappe.enqueue("frappe.utils.now", enqueue_after_commit=True)
		frappe.db.commit()
		self.assertEqual(queue.count, before + 1)
		queue.empty()


class TestHTTP(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		frappe.db.rollback()
		cls.server = subprocess.Popen(["/opt/frappe-test-env/bin/python", "-m", "gunicorn", "--bind", "127.0.0.1:8000", "--workers", "1", "frappe.app:application"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
		cls.base = "http://127.0.0.1:8000"
		for attempt in range(40):
			try:
				if requests.get(cls.base + "/api/method/ping", headers={"Host": SITE}, timeout=2).status_code == 200: break
			except requests.RequestException: pass
			time.sleep(0.25)
		else: raise RuntimeError("Disposable HTTP server failed to start")

	@classmethod
	def tearDownClass(cls):
		cls.server.terminate(); cls.server.wait(timeout=10)

	def session(self, user):
		session = requests.Session(); session.headers["Host"] = SITE
		password = "integration-only-admin" if user == "Administrator" else "integration-only-user-password"
		response = session.post(self.base + "/api/method/login", data={"usr": user, "pwd": password}, timeout=10)
		self.assertEqual(response.status_code, 200, "Fixture login failed")
		return session

	def test_guest_cannot_read_picker_metadata(self):
		response = requests.get(self.base + "/api/method/whatsapp_messaging.utils.get_doctype_fields", headers={"Host": SITE}, params={"doctype": "WhatsApp Message Template", "docname": TEMPLATE}, timeout=10)
		self.assertIn(response.status_code, (401, 403))

	def test_get_cannot_invoke_send_mutation(self):
		response = self.session("Administrator").get(self.base + "/api/method/whatsapp_messaging.controller.wm_handle_on_custom_trigger", params={"template_name": TEMPLATE, "doctype": "ToDo", "docname": "unused"}, timeout=10)
		self.assertIn(response.status_code, (403, 405))

	def test_unrelated_logged_in_user_cannot_send(self):
		response = self.session(UNRELATED).post(self.base + "/api/method/whatsapp_messaging.controller.wm_handle_on_custom_trigger", data={"template_name": TEMPLATE, "doctype": "ToDo", "docname": "unused"}, timeout=10)
		self.assertEqual(response.status_code, 403)
		self.assertEqual(response.json().get("exc_type"), "PermissionError")

	def test_account_resource_never_returns_plaintext_token(self):
		response = self.session("Administrator").get(self.base + "/api/resource/WhatsApp%20Phone%20Number%20ID/" + ACCOUNT, timeout=10)
		self.assertEqual(response.status_code, 200)
		self.assertNotIn(DUMMY_TOKEN, response.text)

	def test_app_roles_can_read_sender_metadata_without_the_token(self):
		for user in (EDITOR, SUPERVISOR):
			response = self.session(user).get(self.base + "/api/resource/WhatsApp%20Phone%20Number%20ID/" + ACCOUNT, timeout=10)
			self.assertEqual(response.status_code, 200)
			self.assertEqual(response.json()["data"]["phone_number_id"], "1234567890")
			self.assertFalse(response.json()["data"].get("access_token"))
			self.assertNotIn(DUMMY_TOKEN, response.text)

	def test_editor_cannot_select_a_secret_field_in_a_list_query(self):
		response = self.session(EDITOR).get(self.base + "/api/resource/WhatsApp%20Phone%20Number%20ID", params={"fields": '["name","access_token"]'}, timeout=10)
		# Frappe 16 removes fields above the caller's read permission level.
		self.assertEqual(response.status_code, 200)
		for row in response.json()["data"]:
			self.assertNotIn("access_token", row)
		self.assertNotIn(DUMMY_TOKEN, response.text)

	def test_editor_can_read_history_through_existing_login(self):
		response = self.session(EDITOR).get(self.base + "/api/resource/WhatsApp%20Conversation/" + CONVERSATION, timeout=10)
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json()["data"]["conversations"][0]["message"], "Fixture history")

	def test_unrelated_login_cannot_read_history(self):
		response = self.session(UNRELATED).get(self.base + "/api/resource/WhatsApp%20Conversation/" + CONVERSATION, timeout=10)
		self.assertEqual(response.status_code, 403)

	def test_editor_cannot_rewrite_history_through_generic_api(self):
		response = self.session(EDITOR).post(self.base + "/api/method/frappe.client.set_value", data={"doctype": "WhatsApp Conversation", "name": CONVERSATION, "fieldname": "recipient", "value": "changed"}, timeout=10)
		self.assertEqual(response.status_code, 403)

	def test_role_capabilities_use_the_existing_session(self):
		for user, bulk in ((EDITOR, False), (SUPERVISOR, True)):
			response = self.session(user).get(self.base + "/api/method/whatsapp_messaging.send_security.get_messaging_access", timeout=10)
			self.assertEqual(response.status_code, 200)
			access = response.json()["message"]
			self.assertTrue(access["can_send"])
			self.assertEqual(access["can_bulk_send"], bulk)
			self.assertFalse(access["can_manage_credentials"])
			self.assertFalse(access["outbound_enabled"])
		response = self.session(UNRELATED).get(self.base + "/api/method/whatsapp_messaging.send_security.get_messaging_access", timeout=10)
		self.assertEqual(response.status_code, 403)

	def test_editor_send_reaches_the_disabled_gate(self):
		response = self.session(EDITOR).post(self.base + "/api/method/whatsapp_messaging.controller.wm_handle_on_custom_trigger", data={"template_name": TEMPLATE, "doctype": "ToDo", "docname": SOURCE}, timeout=10)
		self.assertEqual(response.status_code, 417)
		self.assertIn("Outbound WhatsApp requests are disabled", response.text)

	def test_generic_api_preserves_admin_only_field_configuration(self):
		response = self.session(EDITOR).post(self.base + "/api/method/frappe.client.set_value", data={
			"doctype": "WhatsApp Message Template", "name": TEMPLATE,
			"fieldname": "allowed_source_fields", "value": '["status","allocated_to"]'}, timeout=10)
		self.assertEqual(response.status_code, 200)
		readback = self.session("Administrator").get(self.base + "/api/resource/WhatsApp%20Message%20Template/" + TEMPLATE, timeout=10)
		self.assertEqual(readback.json()["data"]["allowed_source_fields"], '["status"]')

	def test_admin_send_is_stopped_by_default_gate(self):
		response = self.session("Administrator").post(self.base + "/api/method/whatsapp_messaging.controller.wm_handle_on_custom_trigger", data={"template_name": TEMPLATE, "doctype": "ToDo", "docname": SOURCE}, timeout=10)
		self.assertEqual(response.status_code, 417)
		self.assertEqual(response.json().get("exc_type"), "ValidationError")
		self.assertIn("Outbound WhatsApp requests are disabled", response.text)


if __name__ == "__main__":
	os.chdir("/testbench/sites")
	connect()
	try:
		if os.environ.get("WHATSAPP_EXPECT_UPGRADE"):
			legacy = frappe.get_doc("WhatsApp Phone Number ID", "WM Legacy Upgrade")
			assert legacy.meta.get_field("access_token").fieldtype == "Password"
			assert legacy.get_password("access_token") == "integration-only-legacy-token"
			assert legacy.access_token != "integration-only-legacy-token"
			assert frappe.db.exists("Patch Log", {"patch": "whatsapp_messaging.patches.v1_0.encrypt_access_tokens", "skipped": 0})
			assert not frappe.db.get_single_value("WhatsApp Settings", "enable_outbound_messages", cache=False)
			print("PASS: actual old-schema upgrade encrypted the dummy token and left outbound requests disabled", flush=True)
		seed()
		unittest.main(verbosity=2)
	finally:
		frappe.destroy()
