# Copyright (c) 2026, Upeosoft Limited and contributors
# For license information, please see license.txt

"""Whitelisted API for the UpeoXpense single-page app at /upeoxpense.

Every read goes through frappe.get_list (which enforces the caller's row-level
and doctype permissions) - NOT frappe.get_all (which bypasses them). Writes use
ordinary document operations so submit/cancel permissions apply. Nothing here
uses ignore_permissions.

Secrets (WAClient token, Anthropic key) are never returned to the browser; the
settings payload reports only whether each secret is set.
"""

import frappe
from frappe import _
from frappe.utils import flt, get_url_to_form, getdate, now_datetime

from upeo_xpense import pipeline

RECEIPT = "Receipt Capture"
CLAIM = "Expense Claim"
SETTINGS = "UpeoXpense Settings"

# Order used for status pills and grouping in the UI.
RECEIPT_STATUSES = [
	"Queued",
	"Extracting",
	"Awaiting Approval",
	"Approved",
	"Reimbursed",
	"Rejected",
	"Duplicate",
	"Failed",
]

# "Manager and above" - who may approve or reject a logged expense.
APPROVER_ROLES = {"System Manager", "HR Manager", "Expense Approver"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _require_login():
	if frappe.session.user == "Guest":
		raise frappe.PermissionError(_("Please sign in."))


def _is_manager():
	roles = set(frappe.get_roles())
	return bool(roles & {"System Manager", "HR Manager"})


def _can_approve():
	return bool(set(frappe.get_roles()) & APPROVER_ROLES)


def _require_approver():
	if not _can_approve():
		frappe.throw(_("Only a manager can approve or reject expenses."), frappe.PermissionError)


def _file_url(receipt_file):
	return receipt_file or None


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------
@frappe.whitelist()
def bootstrap():
	"""Identity + capabilities the shell needs on first paint."""
	_require_login()
	user = frappe.session.user
	default_currency = frappe.db.get_default("currency") or "KES"
	company = frappe.defaults.get_user_default("company") or frappe.db.get_single_value(
		SETTINGS, "default_company"
	)
	return {
		"user": user,
		"full_name": frappe.utils.get_fullname(user),
		"roles": frappe.get_roles(),
		"is_manager": _is_manager(),
		"can_approve": _can_approve(),
		"can_manage_settings": "System Manager" in frappe.get_roles(),
		"currency": default_currency,
		"company": company,
		"desk_url": get_url_to_form(SETTINGS, SETTINGS),
	}


# ---------------------------------------------------------------------------
# Dashboard / analytics
# ---------------------------------------------------------------------------
@frappe.whitelist()
def dashboard():
	_require_login()

	# One permission-enforcing pull, aggregated in Python. Frappe v16 forbids raw
	# SQL-function strings ("count(name) as count") in get_list fields, and pulling
	# rows keeps row-level permissions intact (frappe.db.sql would not). Receipt
	# volumes for this dashboard are modest.
	receipts_data = frappe.get_list(
		RECEIPT,
		fields=[
			"status",
			"gross_amount",
			"receipt_date",
			"vendor_name",
			"expense_claim_type",
			"suggested_category",
			"needs_claim",
			"creation",
		],
		limit=0,
	)

	status_counts = {s: 0 for s in RECEIPT_STATUSES}
	# Split the pipeline: company-paid expenses vs reimbursable claims are
	# different populations and get their own donut.
	expense_status_counts = {s: 0 for s in RECEIPT_STATUSES}
	claim_status_counts = {s: 0 for s in RECEIPT_STATUSES}
	captured_value = 0.0
	month_count = 0
	month_value = 0.0
	month_start = getdate().replace(day=1)
	trend_map = {}
	vendor_map = {}
	category_map = {}
	# Settlement analytics: where approved money currently sits.
	company_paid_value = 0.0  # petty-cash expenses, already in expense accounts
	pending_reimbursement_value = 0.0  # approved reimbursables, sitting in the hold
	pending_reimbursement_count = 0
	reimbursed_value = 0.0  # refunded to employee, now in expense accounts

	for r in receipts_data:
		status = r.status or "Queued"
		if status in status_counts:
			status_counts[status] += 1
			bucket = claim_status_counts if r.needs_claim else expense_status_counts
			bucket[status] += 1
		amount = flt(r.gross_amount)
		if status in ("Awaiting Approval", "Approved", "Reimbursed"):
			captured_value += amount
		if status == "Approved" and r.needs_claim:
			pending_reimbursement_value += amount
			pending_reimbursement_count += 1
		elif status == "Approved":
			company_paid_value += amount
		elif status == "Reimbursed":
			reimbursed_value += amount
		if r.creation and getdate(r.creation) >= month_start:
			month_count += 1
			month_value += amount
		if r.receipt_date:
			ym = str(r.receipt_date)[:7]
			bucket = trend_map.setdefault(ym, {"total": 0.0, "count": 0})
			bucket["total"] += amount
			bucket["count"] += 1
		if status != "Rejected":
			if r.vendor_name:
				v = vendor_map.setdefault(r.vendor_name, {"total": 0.0, "count": 0})
				v["total"] += amount
				v["count"] += 1
			label = r.expense_claim_type or r.suggested_category or "Uncategorised"
			category_map[label] = category_map.get(label, 0.0) + amount

	total_receipts = sum(status_counts.values())
	trend = [
		{"month": k, "total": v["total"], "count": v["count"]}
		for k, v in sorted(trend_map.items())
	][-6:]
	top_vendors = sorted(
		[{"vendor": k, "total": v["total"], "count": v["count"]} for k, v in vendor_map.items()],
		key=lambda x: x["total"],
		reverse=True,
	)[:6]
	category_split = sorted(
		[{"label": k, "total": v} for k, v in category_map.items()],
		key=lambda x: x["total"],
		reverse=True,
	)[:6]

	# Claims by approval status (aggregated in Python for the same reasons).
	claim_counts = {"Draft": 0, "Approved": 0, "Rejected": 0}
	claim_value = {"Draft": 0.0, "Approved": 0.0, "Rejected": 0.0}
	try:
		for c in frappe.get_list(
			CLAIM, fields=["approval_status", "total_claimed_amount"], limit=0
		):
			if c.approval_status in claim_counts:
				claim_counts[c.approval_status] += 1
				claim_value[c.approval_status] += flt(c.total_claimed_amount)
	except frappe.PermissionError:
		pass

	# Recent activity.
	recent = frappe.get_list(
		RECEIPT,
		fields=[
			"name",
			"vendor_name",
			"gross_amount",
			"currency",
			"status",
			"receipt_date",
			"employee",
			"confidence",
			"modified",
		],
		order_by="modified desc",
		limit=8,
	)

	return {
		"status_counts": status_counts,
		"expense_status_counts": expense_status_counts,
		"claim_status_counts": claim_status_counts,
		"total_receipts": total_receipts,
		"captured_value": captured_value,
		"awaiting_approval": status_counts.get("Awaiting Approval", 0),
		"approved": status_counts.get("Approved", 0),
		"reimbursed": status_counts.get("Reimbursed", 0),
		"failed": status_counts.get("Failed", 0),
		"company_paid_value": company_paid_value,
		"pending_reimbursement_value": pending_reimbursement_value,
		"pending_reimbursement_count": pending_reimbursement_count,
		"reimbursed_value": reimbursed_value,
		"in_expense_accounts_value": company_paid_value + reimbursed_value,
		"month_count": month_count,
		"month_value": month_value,
		"trend": trend,
		"top_vendors": top_vendors,
		"category_split": category_split,
		"claim_counts": claim_counts,
		"claim_value": claim_value,
		"recent": recent,
		"currency": frappe.db.get_default("currency") or "KES",
	}


# ---------------------------------------------------------------------------
# Receipts
# ---------------------------------------------------------------------------
@frappe.whitelist()
def receipts(status=None, search=None, start=0, limit=20):
	_require_login()
	filters = {}
	if status and status != "All":
		filters["status"] = status
	or_filters = None
	if search:
		or_filters = [
			["vendor_name", "like", f"%{search}%"],
			["sender_phone", "like", f"%{search}%"],
			["name", "like", f"%{search}%"],
		]

	rows = frappe.get_list(
		RECEIPT,
		filters=filters,
		or_filters=or_filters,
		fields=[
			"name",
			"vendor_name",
			"gross_amount",
			"vat_amount",
			"currency",
			"status",
			"receipt_date",
			"employee",
			"sender_phone",
			"confidence",
			"expense_claim",
			"expense_claim_type",
			"suggested_category",
			"modified",
			"creation",
		],
		order_by="modified desc",
		start=int(start),
		page_length=int(limit),
	)
	total = len(
		frappe.get_list(RECEIPT, filters=filters, or_filters=or_filters, fields=["name"], limit=0)
	)
	return {"rows": rows, "total": total}


@frappe.whitelist()
def receipt(name):
	_require_login()
	# get_doc enforces read permission on the specific record.
	doc = frappe.get_doc(RECEIPT, name)
	doc.check_permission("read")
	data = doc.as_dict()

	employee_name = None
	if doc.employee:
		employee_name = frappe.db.get_value("Employee", doc.employee, "employee_name")

	claim_info = None
	if doc.expense_claim and frappe.db.exists(CLAIM, doc.expense_claim):
		c = frappe.db.get_value(
			CLAIM,
			doc.expense_claim,
			["name", "approval_status", "docstatus", "total_claimed_amount"],
			as_dict=True,
		)
		claim_info = c

	line_items = []
	if doc.line_items:
		try:
			line_items = frappe.parse_json(doc.line_items) or []
		except Exception:
			line_items = []

	return {
		"doc": data,
		"employee_name": employee_name,
		"image_url": _file_url(doc.receipt_file),
		"claim": claim_info,
		"line_items": line_items,
		"validation_errors": [e for e in (doc.validation_errors or "").splitlines() if e.strip()],
		"can_act": doc.has_permission("write"),
		"can_approve": _can_approve(),
		"reimbursable": bool(doc.needs_claim),
		"can_reimburse": _can_approve() and doc.status == "Approved" and bool(doc.needs_claim),
	}


@frappe.whitelist()
def receipt_action(name, action, amount=None, reason=None, raise_claim=None):
	"""Approve / reject / correct a logged expense. Approve and reject are limited
	to managers (APPROVER_ROLES); both notify the sender on WhatsApp. Correct
	adjusts the amount a manager or the record's editor read wrong. On approve,
	raise_claim also raises a draft reimbursement Expense Claim."""
	_require_login()
	doc = frappe.get_doc(RECEIPT, name)
	settings = frappe.get_cached_doc(SETTINGS)

	if action == "approve":
		_require_approver()
		flag = str(raise_claim).lower() in ("1", "true", "yes", "on")
		pipeline.approve_expense(name, approver=frappe.session.user, raise_claim=flag)
	elif action == "reimburse":
		_require_approver()
		pipeline.reimburse_expense(name, approver=frappe.session.user)
	elif action == "reject":
		_require_approver()
		pipeline.reject_expense(name, reason=reason, approver=frappe.session.user)
	elif action == "correct":
		doc.check_permission("write")
		value = flt(amount)
		if value <= 0:
			frappe.throw(_("Enter an amount greater than zero."))
		pipeline._correct_amount(doc, value, settings)
	else:
		frappe.throw(_("Unknown action."))

	doc.reload()
	return {
		"status": doc.status,
		"gross_amount": doc.gross_amount,
		"rejection_reason": doc.rejection_reason,
	}


# ---------------------------------------------------------------------------
# Expense claims
# ---------------------------------------------------------------------------
@frappe.whitelist()
def claims(status=None, start=0, limit=20):
	_require_login()
	filters = {}
	if status and status != "All":
		filters["approval_status"] = status
	rows = frappe.get_list(
		CLAIM,
		filters=filters,
		fields=[
			"name",
			"employee",
			"employee_name",
			"approval_status",
			"docstatus",
			"posting_date",
			"total_claimed_amount",
			"total_sanctioned_amount",
			"company",
			"modified",
		],
		order_by="modified desc",
		start=int(start),
		page_length=int(limit),
	)
	return {"rows": rows}


@frappe.whitelist()
def claim(name):
	_require_login()
	doc = frappe.get_doc(CLAIM, name)
	doc.check_permission("read")
	expenses = [
		{
			"expense_date": e.expense_date,
			"expense_type": e.expense_type,
			"description": e.description,
			"amount": e.amount,
			"sanctioned_amount": e.sanctioned_amount,
		}
		for e in doc.expenses
	]
	linked_receipt = frappe.db.get_value(RECEIPT, {"expense_claim": name}, "name")
	return {
		"doc": {
			"name": doc.name,
			"employee": doc.employee,
			"employee_name": doc.employee_name,
			"approval_status": doc.approval_status,
			"docstatus": doc.docstatus,
			"posting_date": doc.posting_date,
			"company": doc.company,
			"total_claimed_amount": doc.total_claimed_amount,
			"total_sanctioned_amount": doc.total_sanctioned_amount,
			"remark": doc.remark,
		},
		"expenses": expenses,
		"linked_receipt": linked_receipt,
		"can_approve": doc.has_permission("submit"),
	}


@frappe.whitelist()
def claim_action(name, action, reason=None):
	"""Approve or reject an Expense Claim. Uses hrms's own approval fields, so
	Expense Approver / submit permissions are enforced by the document."""
	_require_login()
	doc = frappe.get_doc(CLAIM, name)

	if action == "approve":
		doc.check_permission("submit")
		doc.approval_status = "Approved"
		if doc.docstatus == 0:
			doc.submit()
		else:
			doc.save()
	elif action == "reject":
		doc.check_permission("submit")
		doc.approval_status = "Rejected"
		if reason:
			doc.remark = reason
		if doc.docstatus == 0:
			doc.submit()
		else:
			doc.save()
	else:
		frappe.throw(_("Unknown action."))

	doc.reload()
	return {"approval_status": doc.approval_status, "docstatus": doc.docstatus}


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
def _settings_doc_readable():
	if "System Manager" not in frappe.get_roles():
		frappe.throw(_("Only a System Manager can view settings."), frappe.PermissionError)


@frappe.whitelist()
def settings_get():
	_settings_doc_readable()
	s = frappe.get_single(SETTINGS)
	return {
		"waclient_base_url": s.waclient_base_url,
		"waclient_instance_id": s.waclient_instance_id,
		"waclient_access_token_set": bool(s.waclient_access_token),
		"anthropic_api_key_set": bool(s.anthropic_api_key),
		"webhook_token": s.webhook_token,
		"webhook_url": frappe.utils.get_url(
			f"/api/method/upeo_xpense.whatsapp.webhook?webhook_token={s.webhook_token}"
		),
		"default_expense_claim_type": s.default_expense_claim_type,
		"default_company": s.default_company,
		"default_cost_center": s.default_cost_center,
		"company_paid_account": s.company_paid_account,
		"reimbursement_hold_account": s.reimbursement_hold_account,
		"reimbursement_payable_account": s.reimbursement_payable_account,
		"reimbursement_paid_from_account": s.reimbursement_paid_from_account,
		"minimum_confidence": s.minimum_confidence,
		"maximum_receipt_age_days": s.maximum_receipt_age_days,
		"test_phone": s.test_phone,
		"expense_claim_types": [
			t.name for t in frappe.get_list("Expense Claim Type", fields=["name"], limit=0)
		],
		"companies": [c.name for c in frappe.get_list("Company", fields=["name"], limit=0)],
		"cost_centers": [
			c.name
			for c in frappe.get_list(
				"Cost Center", filters={"is_group": 0}, fields=["name"], limit=0
			)
		],
		"ledger_accounts": [
			a.name
			for a in frappe.get_list(
				"Account",
				filters={"company": s.default_company, "is_group": 0} if s.default_company else {"is_group": 0},
				fields=["name"],
				order_by="name asc",
				limit=0,
			)
		],
	}


@frappe.whitelist()
def settings_save(payload):
	_settings_doc_readable()
	if isinstance(payload, str):
		payload = frappe.parse_json(payload)
	s = frappe.get_single(SETTINGS)

	plain = [
		"waclient_base_url",
		"waclient_instance_id",
		"default_expense_claim_type",
		"default_company",
		"default_cost_center",
		"company_paid_account",
		"reimbursement_hold_account",
		"reimbursement_payable_account",
		"reimbursement_paid_from_account",
		"minimum_confidence",
		"maximum_receipt_age_days",
		"test_phone",
	]
	for field in plain:
		if field in payload:
			s.set(field, payload[field])

	# Secrets: only overwrite when a non-empty value is supplied.
	for secret in ["waclient_access_token", "anthropic_api_key"]:
		val = payload.get(secret)
		if val:
			s.set(secret, val)

	s.save()  # enforces System Manager write permission on the Single
	frappe.db.commit()
	return settings_get()


@frappe.whitelist()
def test_connection(phone):
	_settings_doc_readable()
	from upeo_xpense import whatsapp

	whatsapp.send_text(phone, "UpeoXpense test message. If you can read this, WAClient is wired up.")
	return {"ok": True}


# ---------------------------------------------------------------------------
# Expense categories (Expense Claim Types mapped to Chart of Accounts)
# ---------------------------------------------------------------------------
def _categories_company():
	company = frappe.db.get_single_value(SETTINGS, "default_company")
	if not company:
		frappe.throw(_("Set a Default Company in Settings before managing categories."))
	return company


@frappe.whitelist()
def expense_categories():
	"""List every Expense Claim Type with the GL account it posts to for the
	default company, plus the expense accounts available to map to."""
	_require_approver()
	company = _categories_company()

	# frappe.get_list enforces the caller's permissions on Expense Claim Type.
	types = frappe.get_list("Expense Claim Type", fields=["name"], order_by="name asc", limit=0)
	categories = []
	for t in types:
		account = frappe.db.get_value(
			"Expense Claim Account", {"parent": t.name, "company": company}, "default_account"
		)
		categories.append({"name": t.name, "account": account})

	accounts = [
		a.name
		for a in frappe.get_list(
			"Account",
			filters={"company": company, "is_group": 0, "root_type": "Expense"},
			fields=["name"],
			order_by="name asc",
			limit=0,
		)
	]
	# Group (parent) accounts a new expense ledger can be created under.
	account_groups = [
		a.name
		for a in frappe.get_list(
			"Account",
			filters={"company": company, "is_group": 1, "root_type": "Expense"},
			fields=["name"],
			order_by="name asc",
			limit=0,
		)
	]
	return {
		"company": company,
		"categories": categories,
		"accounts": accounts,
		"account_groups": account_groups,
	}


@frappe.whitelist()
def expense_category_save(payload):
	"""Create or update an Expense Claim Type and the GL account it books to for
	the default company. The document write enforces the caller's permission on
	Expense Claim Type - nothing here bypasses permissions."""
	_require_approver()
	if isinstance(payload, str):
		payload = frappe.parse_json(payload)

	name = (payload.get("expense_claim_type") or "").strip()
	account = (payload.get("account") or "").strip()
	if not name:
		frappe.throw(_("A category name is required."))

	company = _categories_company()

	if account:
		acc = frappe.db.get_value(
			"Account", account, ["company", "is_group", "root_type"], as_dict=True
		)
		if not acc or acc.company != company:
			frappe.throw(_("Account {0} does not belong to {1}.").format(account, company))
		if acc.is_group:
			frappe.throw(_("Pick a ledger account, not a group account."))

	if frappe.db.exists("Expense Claim Type", name):
		ect = frappe.get_doc("Expense Claim Type", name)
	else:
		ect = frappe.new_doc("Expense Claim Type")
		ect.expense_type = name

	row = next((r for r in ect.accounts if r.company == company), None)
	if account:
		if row:
			row.default_account = account
		else:
			ect.append("accounts", {"company": company, "default_account": account})
	elif row:
		ect.accounts.remove(row)

	ect.save()  # enforces create/write permission on Expense Claim Type
	frappe.db.commit()
	return expense_categories()


@frappe.whitelist()
def expense_category_delete(name):
	"""Delete an Expense Claim Type, but only when nothing uses it. The default
	category is protected, and frappe.delete_doc itself refuses to remove a type
	still linked from any receipt, claim, or vendor mapping."""
	_require_approver()
	if not frappe.db.exists("Expense Claim Type", name):
		return expense_categories()

	if frappe.db.get_single_value(SETTINGS, "default_expense_claim_type") == name:
		frappe.throw(
			_("{0} is the default category. Change the default in Settings before deleting it.").format(name)
		)

	# Friendly, specific messages before falling back to the generic link check.
	if frappe.db.exists("Expense Claim Detail", {"expense_type": name}):
		frappe.throw(_("Cannot delete {0}: it is used on existing expense claims.").format(name))
	if frappe.db.exists(RECEIPT, {"expense_claim_type": name}):
		frappe.throw(_("Cannot delete {0}: it is assigned to one or more receipts.").format(name))
	if frappe.db.exists("Vendor Mapping", {"expense_claim_type": name}):
		frappe.throw(_("Cannot delete {0}: a vendor mapping points to it.").format(name))

	# Catches any other reference and enforces the caller's delete permission.
	frappe.delete_doc("Expense Claim Type", name)
	frappe.db.commit()
	return expense_categories()


@frappe.whitelist()
def expense_account_create(payload):
	"""Create a new expense ledger account in the chart of accounts, under a
	chosen group, so users can map a category to it without leaving the app."""
	_require_approver()
	if isinstance(payload, str):
		payload = frappe.parse_json(payload)

	account_name = (payload.get("account_name") or "").strip()
	parent_account = (payload.get("parent_account") or "").strip()
	if not account_name:
		frappe.throw(_("An account name is required."))
	if not parent_account:
		frappe.throw(_("Choose the group account to create it under."))

	company = _categories_company()
	parent = frappe.db.get_value(
		"Account", parent_account, ["company", "is_group", "root_type"], as_dict=True
	)
	if not parent or parent.company != company:
		frappe.throw(_("Group {0} does not belong to {1}.").format(parent_account, company))
	if not parent.is_group:
		frappe.throw(_("The parent must be a group account."))
	if parent.root_type != "Expense":
		frappe.throw(_("Pick an expense group so the account posts to the profit and loss."))

	acc = frappe.new_doc("Account")
	acc.account_name = account_name
	acc.parent_account = parent_account
	acc.company = company
	acc.is_group = 0
	acc.insert()  # enforces create permission on Account; inherits root/report type
	frappe.db.commit()

	result = expense_categories()
	result["created_account"] = acc.name
	return result
