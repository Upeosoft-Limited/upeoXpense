# Copyright (c) 2026, Upeosoft Limited and contributors
# For license information, please see license.txt

import json

import frappe

NUMBER_CARD_NAME = "Receipts This Month"
WORKSPACE_NAME = "UpeoXpense"


def after_install():
	ensure_setup()


def after_migrate():
	ensure_setup()


def ensure_setup():
	"""Idempotent post-install / post-migrate setup."""
	_ensure_webhook_token()
	_ensure_number_card()
	_link_number_card_to_workspace()
	frappe.db.commit()


def _ensure_webhook_token():
	settings = frappe.get_single("UpeoXpense Settings")
	if not settings.webhook_token:
		settings.webhook_token = frappe.generate_hash(length=24)
		settings.save(ignore_permissions=True)


def _ensure_number_card():
	if frappe.db.exists("Number Card", NUMBER_CARD_NAME):
		return
	card = frappe.new_doc("Number Card")
	card.name = NUMBER_CARD_NAME
	card.label = NUMBER_CARD_NAME
	card.document_type = "Receipt Capture"
	card.function = "Count"
	card.is_public = 1
	card.show_percentage_stats = 0
	card.filters_json = json.dumps([["Receipt Capture", "creation", "Timespan", "this month"]])
	card.insert(ignore_permissions=True)


def _link_number_card_to_workspace():
	if not frappe.db.exists("Workspace", WORKSPACE_NAME):
		return
	workspace = frappe.get_doc("Workspace", WORKSPACE_NAME)
	if any(row.number_card_name == NUMBER_CARD_NAME for row in workspace.number_cards):
		return
	workspace.append("number_cards", {"number_card_name": NUMBER_CARD_NAME, "label": NUMBER_CARD_NAME})
	workspace.save(ignore_permissions=True)
