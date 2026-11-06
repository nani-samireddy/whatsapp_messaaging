"""Prepare one dummy plaintext credential on the old schema, never a real site."""
import json
from pathlib import Path

import frappe

frappe.init(site="whatsapp-test.localhost", sites_path="/testbench/sites")
frappe.connect()
try:
	assert frappe.conf.db_host == "db"
	assert frappe.get_meta("WhatsApp Phone Number ID").get_field("access_token").fieldtype in ("Data", "Password")
	frappe.get_doc({"doctype": "WhatsApp Phone Number ID", "label": "WM Legacy Upgrade",
		"phone_number_id": "1234567891", "access_token": "integration-only-legacy-token"}).insert()
	# Use the baseline's old schema to exercise a real DocType/table rename.
	number = frappe.get_doc({"doctype": "Static Recipient", "label": "WM Upgrade Reception",
		"phone_number": "+12025550126"}).insert()
	if frappe.db.exists('DocType', 'WhatsApp Template Field Policy'):
		frappe.get_doc({'doctype': 'WhatsApp Template Field Policy', 'source_doctype': 'Static Recipient',
			'allowed_fields': '["label"]'}).insert()
	frappe.get_doc({"doctype": "WhatsApp Message Template", "template_name": "WM Upgrade Number Template",
		"phone_number_id": "WM Legacy Upgrade", "template_doctype": "ToDo", "template_event": "Custom",
		"message_preview": "Training message", "disable": 1,
		"other_recipients": [{"static_recipient": number.name}]}).insert()
	frappe.get_doc({'doctype': 'WhatsApp Message Template', 'template_name': 'WM Upgrade Number Source',
		'phone_number_id': 'WM Legacy Upgrade', 'template_doctype': 'Static Recipient', 'disable': 1,
		'message_preview': 'Training only', 'query_filters': json.dumps({'doctype': 'Static Recipient',
			'filters': [['Static Recipient', 'label', '=', 'Static Recipient']]})}).insert()
	if frappe.db.exists("DocType", "WhatsApp Campaign"):
		frappe.get_doc({"doctype": "WhatsApp Campaign", "campaign_name": "WM Upgrade Numbers",
			"message_template": "WM Upgrade Number Template", "phone_number_id": "WM Legacy Upgrade",
			"disable": 1, "other_recipients": [{"static_recipient": number.name}]}).insert()
	fixture = {}
	if frappe.db.exists("DocType", "WhatsApp Record Link"):
		from whatsapp_messaging.messaging.common import digest, insert
		from whatsapp_messaging.messaging.inbox import ensure_peer, ensure_conversation
		linked = insert("WhatsApp Record Link", reference_doctype="Static Recipient", reference_name=number.name,
			link_key=digest(None, "Static Recipient", number.name))
		account = frappe.get_doc("WhatsApp Phone Number ID", "WM Legacy Upgrade")
		contact = ensure_peer("12025550126", account, "Migration Training Contact")
		conversation = ensure_conversation(account, contact)
		message = insert("WhatsApp Message", conversation=conversation.name, account=account.name,
			peer=contact.name, direction="Outbound", status="Unknown", message="Fictional migration test")
		request = insert("WhatsApp Outbox", message=message.name, conversation=conversation.name,
			account=account.name, request_key=digest("migration-unknown-request"), state="Unknown", network_started=1)
		fixture = dict(link=linked.name, contact=contact.name, conversation=conversation.name,
			message=message.name, request=request.name, request_key=request.request_key)
	Path(frappe.get_site_path("private", "plain-language-fixtures.json")).write_text(json.dumps(fixture))
	frappe.get_doc({"doctype": "File", "file_name": "upgrade-training-note.txt", "content": "Fictional migration fixture",
		"is_private": 1, "attached_to_doctype": "Static Recipient", "attached_to_name": number.name}).insert()
	frappe.get_doc({"doctype": "User Permission", "user": "Administrator", "allow": "Static Recipient",
		"for_value": number.name}).insert()
	frappe.db.commit()
	print("Prepared fictional credential, number, selections, file, permission and Inbox link for upgrade test")
finally:
	frappe.destroy()
