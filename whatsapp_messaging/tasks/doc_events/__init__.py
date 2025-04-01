from whatsapp_messaging.controller import whatsapp_messaging_send_message_handler

def on_update_all(doc, method):
	'''
	This function is called when a document is updated.
	'''
	whatsapp_messaging_send_message_handler(doc, ["Update", "Update Field"])

def after_insert_all(doc, method):
	'''
	This function is called after a document is inserted.
	'''
	whatsapp_messaging_send_message_handler(doc, ["Create"])

def on_trash_all(doc, method):
	'''
	This function is called when a document is deleted.
	'''
	whatsapp_messaging_send_message_handler(doc, ["Delete"])

def on_submit_all(doc, method):
	'''
	This function is called when a document is submitted.
	'''
	whatsapp_messaging_send_message_handler(doc, ["Submit"])

def on_cancel_all(doc, method):
	'''
	This function is called when a document is cancelled.
	'''
	whatsapp_messaging_send_message_handler(doc, ["Cancel"])
