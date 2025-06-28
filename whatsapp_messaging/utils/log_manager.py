
import frappe


def log_wa_message( payload, status, media_doc_name = ""):

	# Get the WhatsApp Conversation doc with the phone number.
	# If the conversation does not exist, create a new one.
	conversation_name = frappe.db.exists("WhatsApp Conversation", {"recipient": payload.get("to")})
	if conversation_name:
		conversation = frappe.get_doc("WhatsApp Conversation", conversation_name)
	else:
		conversation = frappe.get_doc({
			"doctype": "WhatsApp Conversation",
			"recipient": payload.get("to"),
			"status": status
		})
		conversation.insert(ignore_permissions=True)
		conversation.save()
	# Create child doc for the WhatsApp Conversation field
	new_conversation_row = conversation.append("conversations", {
		"recipient": payload.get("to"),
		"status": status,
		"message_type": payload.get("type"),
		"message": payload.get("type") == "text" and payload.get("text").get("body") or payload.get(payload.get("type")).get("caption"),
		"media": media_doc_name
	})
	new_conversation_row.insert(ignore_permissions=True)
	new_conversation_row.save()
	new_conversation_row.submit()
