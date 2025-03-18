import frappe
from whatsapp_messaging.controller import ws_handle_on_update, ws_handle_on_create, ws_handle_on_trash, ws_handle_on_submit, ws_handle_on_cancel, ws_handle_scheduled_messages, ws_handle_cron_messages

def on_scheduled_messages():
	'''
	This function is called every minute.
	'''
	# Get the Scheduled Job Type that triggered this function
	job_name = frappe.local.form_dict.get("job_name")
	if not job_name:
		frappe.log_error("No job name found in scheduled execution")
		return

	# Get the related WhatsApp Message Template
	job = frappe.get_doc("Scheduled Job Type", job_name)
	template_name = job.reference_docname

	if template_name:
		ws_handle_scheduled_messages(template_name)

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

def scheduled_every_five_minutes():
	'''
	This function is called every five minutes.
	'''
	ws_handle_cron_messages("Every five minutes")

def scheduled_hourly():
	'''
	This function is called every hour.
	'''
	ws_handle_cron_messages("Hourly")

def scheduled_daily():
	'''
	This function is called every day.
	'''
	ws_handle_cron_messages("Daily")

def scheduled_weekly():
	'''
	This function is called every week.
	'''
	ws_handle_cron_messages("Weekly")

def scheduled_monthly():
	'''
	This function is called every month.
	'''
	ws_handle_cron_messages("Monthly")

def scheduled_quarterly():
	'''
	This function is called every quarter.
	'''
	ws_handle_cron_messages("Quarterly")

def scheduled_semiannual():
	'''
	This function is called every half year.
	'''
	ws_handle_cron_messages("Semiannual")

def scheduled_yearly():
	'''
	This function is called every year.
	'''
	ws_handle_cron_messages("Yearly")
