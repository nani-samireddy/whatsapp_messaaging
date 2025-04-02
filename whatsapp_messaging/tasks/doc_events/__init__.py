from whatsapp_messaging.controller import handle_doc_events

def on_update_all(doc, method):
	'''
	This function is called when a document is updated.
	'''
	handle_doc_events(doc, ["Update", "Update Field"])

def after_insert_all(doc, method):
	'''
	This function is called after a document is inserted.
	'''
	handle_doc_events(doc, ["Create"])

def on_trash_all(doc, method):
	'''
	This function is called when a document is deleted.
	'''
	handle_doc_events(doc, ["Delete"])

def on_submit_all(doc, method):
	'''
	This function is called when a document is submitted.
	'''
	handle_doc_events(doc, ["Submit"])

def on_cancel_all(doc, method):
	'''
	This function is called when a document is cancelled.
	'''
	handle_doc_events(doc, ["Cancel"])
