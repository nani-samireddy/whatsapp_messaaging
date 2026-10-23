"""Move legacy Data tokens to Frappe's encrypted Password store before schema sync.

No document saves, commits, logging, or outbound requests: the patch manager owns
the transaction. Re-running the patch preserves the encrypted value.
"""

import frappe
from frappe.utils.password import get_decrypted_password, set_encrypted_password


DOCTYPE = "WhatsApp Phone Number ID"
FIELD = "access_token"
MASK = "********"


def execute():
	if not frappe.db.table_exists(DOCTYPE):
		return
	for row in frappe.get_all(DOCTYPE, fields=["name", FIELD]):
		value = row.get(FIELD)
		if not value:
			continue
		if set(value) == {"*"}:
			# A previously migrated record must still have a decryptable credential.
			# Do not replace a masked/missing credential with the mask itself.
			if not get_decrypted_password(DOCTYPE, row.name, FIELD, raise_exception=False):
				frappe.throw("A masked WhatsApp credential has no encrypted value; restore it before migrating")
			continue
		set_encrypted_password(DOCTYPE, row.name, value, FIELD)
		frappe.db.set_value(DOCTYPE, row.name, FIELD, MASK, update_modified=False)
