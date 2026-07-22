# Copyright (c) 2026, Upeosoft Limited and contributors
# For license information, please see license.txt

"""Controller for the UpeoXpense single-page app served at /upeoxpense.

Guests are redirected to the login page (and sent back here afterwards).
Logged-in users get a CSRF token so the SPA can POST to whitelisted methods.
"""

import frappe


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/upeoxpense"
		raise frappe.Redirect

	context.no_cache = 1
	context.csrf_token = frappe.sessions.get_csrf_token()
	context.boot_user = frappe.session.user
	context.boot_full_name = frappe.utils.get_fullname(frappe.session.user)
	return context
