import frappe
from whatsapp_messaging.controller import ws_handle_on_update, ws_handle_on_create, ws_handle_on_trash, ws_handle_on_submit, ws_handle_on_cancel, ws_handle_scheduled_messages

def on_update_all(doc, method):
	'''
	This function is called when a document is updated.
	'''
	ws_handle_on_update(doc, method)

def after_insert_all(doc, method):
	'''
	This function is called after a document is inserted.
	'''
	ws_handle_on_create(doc, method)

def on_trash_all(doc, method):
	'''
	This function is called when a document is deleted.
	'''
	ws_handle_on_trash(doc, method)

def on_submit_all(doc, method):
	'''
	This function is called when a document is submitted.
	'''
	ws_handle_on_submit(doc, method)

def on_cancel_all(doc, method):
	'''
	This function is called when a document is cancelled.
	'''
	ws_handle_on_cancel(doc, method)

def scheduled_task_all():
	'''
	This function is called for all scheduled tasks.
	'''
	frappe.log_error('Scheduled task all called')
	# Check if there are any scheduled messages to be sent.
	ws_handle_scheduled_messages()
