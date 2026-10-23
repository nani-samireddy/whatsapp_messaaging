"""Prepare one dummy plaintext credential on the old schema, never a real site."""
import frappe

frappe.init(site="whatsapp-test.localhost", sites_path="/testbench/sites")
frappe.connect()
try:
	assert frappe.conf.db_host == "db"
	assert frappe.get_meta("WhatsApp Phone Number ID").get_field("access_token").fieldtype == "Data"
	frappe.get_doc({"doctype": "WhatsApp Phone Number ID", "label": "WM Legacy Upgrade",
		"phone_number_id": "1234567891", "access_token": "integration-only-legacy-token"}).insert()
	frappe.db.commit()
	print("Prepared dummy legacy Data credential for upgrade test")
finally:
	frappe.destroy()
