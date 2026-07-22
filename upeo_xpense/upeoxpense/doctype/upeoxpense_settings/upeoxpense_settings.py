# Copyright (c) 2026, Upeosoft Limited and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class UpeoXpenseSettings(Document):
	pass


@frappe.whitelist()
def test_connection(phone: str):
	"""Send a test WhatsApp message so the integration can be verified before
	anything else is built. Called from the Settings form button."""
	frappe.only_for("System Manager")

	phone = (phone or "").strip()
	if not phone:
		frappe.throw("Enter a test phone number first.")

	# Imported here to keep the provider isolated in one module.
	from upeo_xpense.whatsapp import send_text

	send_text(phone, "UpeoXpense test message. If you can read this, WhatsApp send is working.")
	return {"ok": True, "phone": phone}
