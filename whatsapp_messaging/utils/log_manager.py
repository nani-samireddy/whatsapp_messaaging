
import frappe


def log_wa_message(payload, status, media_doc_name=""):
	"""Persist a WhatsApp message to conversation logs safely.

	- Ensures a parent WhatsApp Conversation exists per recipient.
	- Appends a child row using defined child fields.
	"""
	to = (payload or {}).get("to")
	if not to:
		return

	conversation_name = frappe.db.exists("WhatsApp Conversation", {"recipient": to})
	if conversation_name:
		conversation = frappe.get_doc("WhatsApp Conversation", conversation_name)
	else:
		conversation = frappe.get_doc({
			"doctype": "WhatsApp Conversation",
			"recipient": to,
		})
		conversation.insert(ignore_permissions=True)

	msg_type = (payload or {}).get("type")
	message_text = ""
	try:
		if msg_type == "text":
			message_text = ((payload.get("text") or {}).get("body")) or ""
		else:
			media_part = (payload.get(msg_type) or {})
			message_text = media_part.get("caption") or ""
	except Exception:
		message_text = ""

	conversation.append("conversations", {
		"from": "Frappe",
		"status": status,
		"message_type": msg_type,
		"message": message_text,
		"media": media_doc_name or None,
	})
	conversation.save(ignore_permissions=True)
