# Copyright (c) 2026, Upeosoft Limited and contributors
# For license information, please see license.txt

"""The receipt pipeline.

Rules that shape this file:
- Never let Claude make a decision. It returns data with a confidence score.
  Python decides what happens next.
- Every receipt image is kept permanently. It is the audit artifact.
- Respect Frappe permissions. The pipeline runs server-side as Administrator (a
  trusted system actor), never with ignore_permissions=True.
- Never lose a receipt. Failures are recorded on the Receipt Capture.
"""

import base64
import hashlib
import io
import json
import os
import re
from datetime import date

import requests

import frappe
from frappe.utils import add_to_date, flt, getdate, now_datetime, today

from upeo_xpense import validators

# First pass is the cheap, fast model; retry once with the stronger model.
MODEL_FIRST = "claude-haiku-4-5-20251001"
MODEL_RETRY = "claude-opus-4-8"

# Backoff schedule for network / 5xx failures: 1m, 5m, 15m, 1h, then give up.
BACKOFF_SECONDS = [60, 300, 900, 3600]

REQUEST_TIMEOUT = 30

OK_WORDS = {"ok", "yes", "sawa", "1"}
NO_WORDS = {"no", "cancel", "2"}
CLAIM_WORDS = {"claim", "reimburse", "reimbursement", "refund", "3"}

PAYMENT_METHODS = {"Cash", "Card", "M-Pesa", "Bank", "Other"}

_PROMPT_PATH = os.path.join(os.path.dirname(__file__), "prompts", "extract_v1.txt")


class _RetryableError(Exception):
	"""A transient failure (network or 5xx) that should be retried with backoff."""


# ---------------------------------------------------------------------------
# Entry point from the webhook
# ---------------------------------------------------------------------------
def handle_incoming(payload):
	"""Dispatch an incoming WhatsApp message. Runs as a background job."""
	frappe.set_user("Administrator")
	from upeo_xpense import whatsapp

	try:
		parsed = whatsapp.parse_webhook(payload)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "UpeoXpense parse_webhook")
		return

	if not parsed:
		return

	phone = parsed["sender_phone"]

	# Only ever respond to a number that belongs to a known, Active Employee.
	# WAClient forwards every message the WhatsApp account can see - wrong
	# numbers, customers, group chats - and we must never send an unsolicited
	# "send a receipt" prompt to someone who did not opt in by being an
	# employee. Unknown senders are ignored in complete silence.
	if not find_employee(phone):
		return

	try:
		if parsed["message_type"] == "image" and parsed.get("media_url"):
			ingest(
				phone,
				parsed["media_url"],
				parsed.get("caption") or parsed.get("text"),
				media_key=parsed.get("media_key"),
				media_type=parsed.get("media_type") or "image",
			)
		elif parsed["message_type"] == "text" and parsed.get("text"):
			handle_reply(phone, parsed["text"])
		else:
			_safe_send(phone, "Please send a clear photo of a receipt to log an expense.")
	except Exception:
		frappe.log_error(frappe.get_traceback(), "UpeoXpense handle_incoming")


# ---------------------------------------------------------------------------
# Employee lookup by phone
# ---------------------------------------------------------------------------
def phone_variants(raw):
	"""Return plausible stored formats for a phone number, normalising +, spaces,
	and leading 254 vs 0."""
	digits = "".join(ch for ch in str(raw or "") if ch.isdigit())
	if not digits:
		return []
	core = digits
	if core.startswith("254"):
		core = core[3:]
	elif core.startswith("0"):
		core = core[1:]
	variants = {digits, core, "0" + core, "254" + core, "+254" + core}
	return [v for v in variants if v]


def find_employee(phone):
	"""Look up an Active Employee by cell_number, tolerant of phone formatting."""
	variants = phone_variants(phone)
	if not variants:
		return None

	name = frappe.db.get_value(
		"Employee", {"cell_number": ["in", variants], "status": "Active"}, "name"
	)
	if name:
		return name

	# Fallback: normalise both sides. Handles cell numbers stored with spaces or +.
	target = set(variants)
	for row in frappe.get_all(
		"Employee", filters={"status": "Active"}, fields=["name", "cell_number"]
	):
		if row.cell_number and target & set(phone_variants(row.cell_number)):
			return row.name
	return None


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------
def ingest(sender_phone, media_url, caption=None, media_key=None, media_type="image"):
	"""Download the media, attach it to a new Receipt Capture, dedupe by hash,
	and enqueue extraction. WhatsApp media arrives encrypted (a '.enc' URL plus a
	media_key); whatsapp.fetch_media decrypts it."""
	frappe.set_user("Administrator")

	employee = find_employee(sender_phone)
	if not employee:
		_safe_send(
			sender_phone,
			"We could not match your number to an employee record. Please contact the admin.",
		)
		return

	try:
		from upeo_xpense import whatsapp

		content = whatsapp.fetch_media(media_url, media_key=media_key, media_type=media_type)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "UpeoXpense media download")
		_safe_send(sender_phone, "We could not download your receipt image. Please try again.")
		return

	if not content:
		_safe_send(sender_phone, "Your receipt image was empty. Please try again.")
		return

	file_hash = hashlib.sha256(content).hexdigest()
	phash = _image_phash(content)
	filename = _filename_from_url(media_url, file_hash)

	# Exact-bytes match, or a perceptual match (same photo re-sent - WhatsApp
	# re-compresses on every send, so the exact hash differs but the perceptual
	# hash stays close). This catches re-uploads regardless of how Claude reads them.
	existing = frappe.db.get_value("Receipt Capture", {"file_hash": file_hash}, "name")
	if not existing and phash:
		existing = _find_perceptual_duplicate(phash)
	if existing:
		dup = frappe.new_doc("Receipt Capture")
		dup.employee = employee
		dup.sender_phone = sender_phone
		dup.status = "Duplicate"
		dup.duplicate_of = existing
		dup.notes = caption
		dup.file_hash = file_hash
		dup.image_phash = phash
		dup.error_message = f"Duplicate of {existing}"
		dup.insert()
		_attach(dup, filename, content, df="receipt_file")
		frappe.db.commit()
		_safe_send(sender_phone, "We already have this receipt, so we did not log it again.")
		return

	doc = frappe.new_doc("Receipt Capture")
	doc.employee = employee
	doc.sender_phone = sender_phone
	doc.status = "Queued"
	doc.file_hash = file_hash
	doc.image_phash = phash
	doc.notes = caption
	doc.insert()
	_attach(doc, filename, content, df="receipt_file")
	frappe.db.commit()

	frappe.enqueue("upeo_xpense.pipeline.extract", queue="default", docname=doc.name)


def _filename_from_url(url, file_hash):
	ext = ".jpg"
	tail = url.split("?")[0].rsplit("/", 1)[-1]
	if "." in tail:
		candidate = "." + tail.rsplit(".", 1)[-1].lower()
		if candidate in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".pdf", ".heic"):
			ext = candidate
	return f"receipt-{file_hash[:12]}{ext}"


def _attach(doc, filename, content, df=None):
	"""Save the bytes as a private File attached to doc, and set the field."""
	from frappe.utils.file_manager import save_file

	file_doc = save_file(filename, content, doc.doctype, doc.name, is_private=1, df=df)
	if df:
		doc.db_set(df, file_doc.file_url)
	return file_doc


# ---------------------------------------------------------------------------
# Preprocess and extract
# ---------------------------------------------------------------------------
def preprocess(doc):
	"""EXIF transpose, autocontrast, resize to 1500px on the long edge, JPEG q85.
	Returns base64 text. Does not modify the stored original."""
	from PIL import Image, ImageOps

	content = _original_bytes(doc)
	if not content:
		raise ValueError("No original image to preprocess.")

	image = Image.open(io.BytesIO(content))
	image = ImageOps.exif_transpose(image)
	if image.mode != "RGB":
		image = image.convert("RGB")
	image = ImageOps.autocontrast(image)
	image.thumbnail((1500, 1500), Image.LANCZOS)

	buffer = io.BytesIO()
	image.save(buffer, format="JPEG", quality=85)
	return base64.b64encode(buffer.getvalue()).decode("ascii")


def _original_bytes(doc):
	if not doc.receipt_file:
		return None
	file_name = frappe.db.get_value("File", {"file_url": doc.receipt_file}, "name")
	if not file_name:
		return None
	return frappe.get_doc("File", file_name).get_content()


def extract(docname):
	"""Send the preprocessed image to Claude and apply the result. Runs as a job."""
	frappe.set_user("Administrator")
	doc = frappe.get_doc("Receipt Capture", docname)
	if doc.status in ("Confirmed", "Rejected", "Duplicate"):
		return

	doc.db_set("status", "Extracting")
	doc.db_set("next_retry_at", None)

	settings = frappe.get_cached_doc("UpeoXpense Settings")

	try:
		image_b64 = preprocess(doc)
	except Exception as exc:
		_fail(doc, f"Could not process the image: {exc}")
		return

	threshold = settings.minimum_confidence or 0.7
	try:
		result, raw_text = _extract_with_models(image_b64, settings, threshold)
	except _RetryableError as exc:
		_schedule_retry(doc, str(exc))
		return
	except Exception as exc:
		# Non-retryable (bad key, refusal, etc.). Store what we can and fail.
		doc.db_set("raw_extract", json.dumps({"error": str(exc)}))
		_fail(doc, f"Extraction failed: {exc}")
		return

	# Store the raw response verbatim, always.
	doc.db_set("raw_extract", raw_text)
	_apply_extract(doc, result)
	frappe.db.commit()

	finalize(doc.name)


def _load_prompt():
	with open(_PROMPT_PATH, encoding="utf-8") as handle:
		return handle.read()


def _extract_with_models(image_b64, settings, threshold):
	"""Try the fast model; if confidence is low or a required field is null,
	retry once with the stronger model. Returns (result_dict, raw_text)."""
	api_key = settings.get_password("anthropic_api_key") if settings.anthropic_api_key else None
	if not api_key:
		raise Exception("Anthropic API key is not configured in UpeoXpense Settings.")

	prompt = _load_prompt()

	parsed, raw = _call_claude(MODEL_FIRST, image_b64, prompt, api_key)
	if _needs_retry(parsed, threshold):
		parsed_retry, raw_retry = _call_claude(MODEL_RETRY, image_b64, prompt, api_key)
		if parsed_retry is not None:
			return parsed_retry, raw_retry
		return (parsed or {}), (raw_retry or raw)
	return (parsed or {}), raw


def _needs_retry(parsed, threshold):
	if parsed is None:
		return True
	confidence = parsed.get("confidence")
	if confidence is None:
		return True
	try:
		if float(confidence) < float(threshold):
			return True
	except (ValueError, TypeError):
		return True
	# Required fields.
	if parsed.get("gross_amount") in (None, "") or parsed.get("receipt_date") in (None, ""):
		return True
	return False


def _call_claude(model, image_b64, prompt, api_key):
	"""Call Claude with the image. Returns (parsed_dict_or_None, raw_text).
	Raises _RetryableError on network / 5xx failures."""
	import anthropic

	client = anthropic.Anthropic(api_key=api_key)
	try:
		message = client.messages.create(
			model=model,
			max_tokens=1024,
			messages=[
				{
					"role": "user",
					"content": [
						{
							"type": "image",
							"source": {
								"type": "base64",
								"media_type": "image/jpeg",
								"data": image_b64,
							},
						},
						{"type": "text", "text": prompt},
					],
				}
			],
		)
	except (anthropic.APIConnectionError, anthropic.RateLimitError, anthropic.InternalServerError) as exc:
		raise _RetryableError(str(exc))
	except anthropic.APIStatusError as exc:
		if getattr(exc, "status_code", 500) >= 500:
			raise _RetryableError(str(exc))
		raise

	raw = "".join(
		block.text for block in message.content if getattr(block, "type", None) == "text"
	)
	return _parse_json(raw), raw


def _parse_json(raw):
	if not raw:
		return None
	try:
		return json.loads(raw)
	except (ValueError, TypeError):
		pass
	match = re.search(r"\{.*\}", raw, re.DOTALL)
	if match:
		try:
			return json.loads(match.group(0))
		except (ValueError, TypeError):
			return None
	return None


def _apply_extract(doc, result):
	result = result or {}

	doc.vendor_name = _clean_str(result.get("vendor_name"))
	doc.receipt_date = _clean_date(result.get("receipt_date"))
	doc.currency = _clean_str(result.get("currency")) or doc.currency or "KES"
	doc.gross_amount = _clean_number(result.get("gross_amount"))
	doc.vat_amount = _clean_number(result.get("vat_amount"))
	doc.kra_pin = _clean_str(result.get("kra_pin"))
	doc.etims_invoice_number = _clean_str(result.get("etims_invoice_number"))
	doc.receipt_number = _clean_str(result.get("receipt_number"))

	method = _clean_str(result.get("payment_method"))
	doc.payment_method = method if method in PAYMENT_METHODS else None

	doc.vendor_email = _clean_str(result.get("vendor_email"))

	# Store the line items (what was bought) as JSON for display.
	items = result.get("line_items")
	if isinstance(items, list) and items:
		clean_items = []
		for it in items:
			if not isinstance(it, dict):
				continue
			desc = _clean_str(it.get("description"))
			if not desc:
				continue
			clean_items.append(
				{"description": desc, "qty": _clean_number(it.get("qty")), "amount": _clean_number(it.get("amount"))}
			)
		doc.line_items = json.dumps(clean_items) if clean_items else None
	else:
		doc.line_items = None

	doc.suggested_category = _clean_str(result.get("suggested_category"))

	confidence = result.get("confidence")
	try:
		doc.confidence = float(confidence) if confidence is not None else 0
	except (ValueError, TypeError):
		doc.confidence = 0

	doc.save()


# ---------------------------------------------------------------------------
# Validate, draft, confirm
# ---------------------------------------------------------------------------
def finalize(docname):
	doc = frappe.get_doc("Receipt Capture", docname)
	settings = frappe.get_cached_doc("UpeoXpense Settings")

	errors = validators.validate(
		doc.gross_amount,
		doc.vat_amount,
		doc.receipt_date,
		doc.kra_pin,
		settings.maximum_receipt_age_days,
	)
	doc.db_set("validation_errors", "\n".join(errors) if errors else None)

	# We cannot log an expense without an amount. Treat as a read failure.
	if not doc.gross_amount or float(doc.gross_amount) <= 0:
		_fail(doc, "Amount could not be read.")
		_safe_send(
			doc.sender_phone,
			"We could not read the amount on your receipt. Please send a clearer photo.",
		)
		return

	# Semantic duplicate guard. The file-hash check in ingest only catches identical
	# bytes; WhatsApp re-encodes an image on every send, so a re-upload has a different
	# hash. Match on the extracted content (same employee, vendor, amount and date).
	dupe = _find_duplicate(doc)
	if dupe:
		doc.db_set("status", "Duplicate")
		doc.db_set("duplicate_of", dupe)
		doc.db_set("error_message", f"Looks like a duplicate of {dupe}.")
		frappe.db.commit()
		_safe_send(
			doc.sender_phone,
			"We already have this receipt (same vendor, amount and date), so we did not log it again.",
		)
		return

	submit_for_approval(doc.name)


# Perceptual-hash duplicate detection ---------------------------------------
# Standalone perceptual match (no other corroboration) must be tight.
PHASH_STRICT = 12
# When the exact amount already matches, a looser perceptual match is safe.
PHASH_LOOSE = 18


def _vendor_similar(a, b):
	"""True if two vendor names are the same allowing for OCR slips (PLANLINK vs
	PLANTLINK). Compares alphanumeric-only, lowercased."""
	na = "".join(ch for ch in (a or "").lower() if ch.isalnum())
	nb = "".join(ch for ch in (b or "").lower() if ch.isalnum())
	if not na or not nb:
		return False
	if na == nb:
		return True
	short, long = (na, nb) if len(na) <= len(nb) else (nb, na)
	if short and short in long:
		return True
	return _levenshtein(na, nb) <= max(2, len(long) // 6)


def _levenshtein(a, b):
	if a == b:
		return 0
	prev = list(range(len(b) + 1))
	for i, ca in enumerate(a, 1):
		cur = [i]
		for j, cb in enumerate(b, 1):
			cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
		prev = cur
	return prev[-1]


def _image_phash(content):
	"""64-bit dHash of the image. Robust to WhatsApp's re-compression, so the same
	photo re-sent yields a near-identical hash. Returns a 16-char hex string."""
	from PIL import Image

	try:
		image = Image.open(io.BytesIO(content)).convert("L").resize((9, 8), Image.LANCZOS)
	except Exception:
		return None
	pixels = list(image.getdata())
	bits = 0
	for row in range(8):
		for col in range(8):
			left = pixels[row * 9 + col]
			right = pixels[row * 9 + col + 1]
			bits = (bits << 1) | (1 if left > right else 0)
	return "%016x" % bits


def _phash_distance(a, b):
	try:
		return bin(int(a, 16) ^ int(b, 16)).count("1")
	except (ValueError, TypeError):
		return 64


def _find_perceptual_duplicate(phash, exclude_name=None, before=None, threshold=PHASH_STRICT):
	"""Return an earlier receipt whose image is perceptually the same, or None."""
	if not phash:
		return None
	filters = {"image_phash": ["is", "set"], "status": ["!=", "Failed"]}
	if exclude_name:
		filters["name"] = ["!=", exclude_name]
	if before:
		filters["creation"] = ["<", before]
	rows = frappe.get_all(
		"Receipt Capture", filters=filters, fields=["name", "image_phash"], order_by="creation asc"
	)
	for r in rows:
		if r.image_phash and _phash_distance(phash, r.image_phash) <= threshold:
			return r.name
	return None


def _find_duplicate(doc):
	"""Detect a re-uploaded receipt. Two signals, strongest first:

	1. The printed receipt / eTIMS number - a hard identifier for one physical
	   receipt, matched company-wide (a receipt is a duplicate no matter who sends
	   it). Read may miss it, hence the fallback.
	2. Same employee + vendor + amount + date.

	We deliberately match receipts in ANY status except Failed (which never has an
	amount) - re-sending a receipt that was already rejected is still a duplicate,
	not a fresh submission.
	"""
	# Only earlier receipts can be the original this one duplicates.
	earlier = {"name": ["!=", doc.name], "status": ["!=", "Failed"]}
	if doc.creation:
		earlier["creation"] = ["<", doc.creation]

	# 0) Same photo (perceptual hash) - most robust against OCR variance.
	near = _find_perceptual_duplicate(doc.image_phash, exclude_name=doc.name, before=doc.creation)
	if near:
		return near

	# 1) By printed number (cross-field, company-wide): the same number can land in
	# etims on one read and receipt_number on another.
	numbers = {n for n in (doc.get("etims_invoice_number"), doc.get("receipt_number")) if n}
	for num in numbers:
		match = frappe.db.get_value(
			"Receipt Capture", {**earlier, "etims_invoice_number": num}, "name"
		) or frappe.db.get_value("Receipt Capture", {**earlier, "receipt_number": num}, "name")
		if match:
			return match

	# 2) By content: the amount reads exactly the same every time, so anchor on
	# (same employee + same exact amount) and require ONE corroborating signal -
	# same date, a fuzzy-matching vendor, or a loose perceptual match - so OCR slips
	# in the vendor or date do not let a re-upload through.
	if not (doc.gross_amount and doc.employee):
		return None
	candidates = frappe.get_all(
		"Receipt Capture",
		filters={**earlier, "employee": doc.employee, "gross_amount": doc.gross_amount},
		fields=["name", "vendor_name", "receipt_date", "image_phash"],
		order_by="creation asc",
	)
	for c in candidates:
		same_date = doc.receipt_date and c.receipt_date and str(doc.receipt_date) == str(c.receipt_date)
		vendor_ok = _vendor_similar(doc.vendor_name, c.vendor_name)
		phash_ok = (
			doc.image_phash
			and c.image_phash
			and _phash_distance(doc.image_phash, c.image_phash) <= PHASH_LOOSE
		)
		if same_date or vendor_ok or phash_ok:
			return c.name
	return None


def _expense_account(expense_type, company):
	"""The GL expense account mapped to this Expense Claim Type for this company.
	HRMS fetches this client-side from the type; server-side inserts must set it
	explicitly or the submit fails with 'Account is required' on the GL entry."""
	if not (expense_type and company):
		return None
	return frappe.db.get_value(
		"Expense Claim Account",
		{"parent": expense_type, "company": company},
		"default_account",
	)


def _resolve_expense_claim_type(doc, settings):
	# Vendor Mapping first, so corrections stick.
	if doc.vendor_name:
		mapped = frappe.db.get_value(
			"Vendor Mapping", {"vendor_name": doc.vendor_name}, "expense_claim_type"
		)
		if mapped:
			return mapped
	# Then Claude's suggestion, only if it is a real Expense Claim Type.
	if doc.suggested_category and frappe.db.exists("Expense Claim Type", doc.suggested_category):
		return doc.suggested_category
	# Then the default from Settings.
	return settings.default_expense_claim_type


def submit_for_approval(docname):
	"""Log the expense for a manager to approve. We do NOT create an Expense Claim -
	many of these are paid from petty cash. The Receipt Capture itself is the
	expense record; a manager approves or rejects it."""
	doc = frappe.get_doc("Receipt Capture", docname)
	settings = frappe.get_cached_doc("UpeoXpense Settings")

	# Resolve a category label (Vendor Mapping -> Claude suggestion -> default).
	category = _resolve_expense_claim_type(doc, settings)
	if category:
		doc.db_set("expense_claim_type", category)

	doc.db_set("status", "Awaiting Approval")
	frappe.db.commit()

	_safe_send(doc.sender_phone, confirmation_message(doc))


def _mark_needs_claim(doc):
	"""The sender asks for this expense to be reimbursed via a claim."""
	doc.db_set("needs_claim", 1)
	frappe.db.commit()
	_safe_send(
		doc.sender_phone,
		"Noted. You will be reimbursed for this once a manager approves it.",
	)


# ---------------------------------------------------------------------------
# Settlement accounting
#
# A company-paid (petty cash) expense is recognised immediately on approval:
#     Dr  category expense account
#     Cr  company-paid-from account (cash)
#
# A reimbursable expense (the employee paid, the company owes them) is parked in
# a temporary hold on approval, and only becomes an expense once the employee is
# refunded:
#     approve:    Dr hold            Cr reimbursement payable
#     reimburse:  Dr expense account Cr hold            (recognise the expense)
#                 Dr payable         Cr paid-from cash  (refund the employee)
# ---------------------------------------------------------------------------
def _settlement_company(doc, settings):
	return frappe.db.get_value("Employee", doc.employee, "company") or settings.default_company


def _settlement_cost_center(company, settings):
	return settings.get("default_cost_center") or (
		frappe.get_cached_value("Company", company, "cost_center") if company else None
	)


def _resolved_expense_account(doc, settings, company):
	"""The GL expense account for this receipt's category, or throw a clear
	message naming the category that needs mapping."""
	category = doc.expense_claim_type or _resolve_expense_claim_type(doc, settings)
	account = _expense_account(category, company)
	if not account:
		frappe.throw(
			f"Category '{category or 'Uncategorised'}' is not mapped to an account. "
			f"Map it on the Categories page before posting this expense."
		)
	return account


def _je_line(account, debit, credit, cost_center):
	return {
		"account": account,
		"cost_center": cost_center,
		"debit_in_account_currency": flt(debit),
		"credit_in_account_currency": flt(credit),
	}


def _post_journal(company, posting_date, lines, remark):
	"""Create and submit a Journal Entry, returning its name."""
	je = frappe.new_doc("Journal Entry")
	je.voucher_type = "Journal Entry"
	je.company = company
	je.posting_date = posting_date
	je.user_remark = remark
	for line in lines:
		je.append("accounts", line)
	je.insert()
	je.submit()
	return je.name


def approve_expense(docname, approver=None, raise_claim=False):
	"""Manager approves a logged expense. Company-paid expenses post straight to
	the expense account; reimbursable ones (needs_claim, or raise_claim) are held
	in the temporary hold account until the employee is refunded."""
	doc = frappe.get_doc("Receipt Capture", docname)
	settings = frappe.get_cached_doc("UpeoXpense Settings")

	if raise_claim:
		doc.db_set("needs_claim", 1)
		doc.reload()

	company = _settlement_company(doc, settings)
	cost_center = _settlement_cost_center(company, settings)
	# Book on the approval date; the receipt date can fall in a closed or not-yet
	# open fiscal year, which the ledger rejects.
	posting_date = today()
	amount = flt(doc.gross_amount)
	tag = f"{doc.name} {doc.vendor_name or 'receipt'}"
	# Validate the expense account up front for both paths (reimbursables need it
	# at refund time), so we never approve something we cannot post.
	expense_account = _resolved_expense_account(doc, settings, company)

	if doc.needs_claim:
		hold = settings.get("reimbursement_hold_account")
		payable = settings.get("reimbursement_payable_account")
		if not (hold and payable):
			frappe.throw("Set the reimbursement hold and payable accounts in Settings first.")
		je = _post_journal(
			company,
			posting_date,
			[_je_line(hold, amount, 0, cost_center), _je_line(payable, 0, amount, cost_center)],
			f"Reimbursable expense approved, held pending reimbursement: {tag}",
		)
	else:
		source = settings.get("company_paid_account") or frappe.get_cached_value(
			"Company", company, "default_cash_account"
		)
		if not source:
			frappe.throw("Set a company-paid (cash) account in Settings first.")
		je = _post_journal(
			company,
			posting_date,
			[_je_line(expense_account, amount, 0, cost_center), _je_line(source, 0, amount, cost_center)],
			f"Company-paid expense: {tag}",
		)

	doc.db_set("status", "Approved")
	doc.db_set("journal_entry", je)
	doc.db_set("rejection_reason", None)
	doc.db_set("decided_by", approver or frappe.session.user)
	doc.db_set("decided_at", now_datetime())
	frappe.db.commit()

	amount_txt = _money(doc.currency or "KES", doc.gross_amount)
	vendor = doc.vendor_name or "receipt"
	if doc.needs_claim:
		_safe_send(
			doc.sender_phone,
			f"Your expense of {amount_txt} ({vendor}) was approved and is pending reimbursement.",
		)
	else:
		_safe_send(doc.sender_phone, f"Your expense of {amount_txt} ({vendor}) was approved.")


def reimburse_expense(docname, approver=None):
	"""Mark an approved reimbursable expense as refunded to the employee. This is
	the point the amount leaves the temporary hold and becomes a real expense."""
	doc = frappe.get_doc("Receipt Capture", docname)
	settings = frappe.get_cached_doc("UpeoXpense Settings")

	if doc.status != "Approved" or not doc.needs_claim:
		frappe.throw("Only an approved reimbursable expense can be marked reimbursed.")

	company = _settlement_company(doc, settings)
	cost_center = _settlement_cost_center(company, settings)
	expense_account = _resolved_expense_account(doc, settings, company)
	hold = settings.get("reimbursement_hold_account")
	payable = settings.get("reimbursement_payable_account")
	paid_from = settings.get("reimbursement_paid_from_account") or frappe.get_cached_value(
		"Company", company, "default_cash_account"
	)
	if not (hold and payable and paid_from):
		frappe.throw("Set the reimbursement accounts in Settings first.")

	amount = flt(doc.gross_amount)
	je = _post_journal(
		company,
		today(),
		[
			_je_line(expense_account, amount, 0, cost_center),  # recognise the expense
			_je_line(hold, 0, amount, cost_center),  # clear the hold
			_je_line(payable, amount, 0, cost_center),  # settle what we owed
			_je_line(paid_from, 0, amount, cost_center),  # cash out to the employee
		],
		f"Reimbursement paid to employee: {doc.name} {doc.vendor_name or 'receipt'}",
	)

	doc.db_set("status", "Reimbursed")
	doc.db_set("reimbursement_journal_entry", je)
	doc.db_set("reimbursed_by", approver or frappe.session.user)
	doc.db_set("reimbursed_at", now_datetime())
	frappe.db.commit()

	_safe_send(
		doc.sender_phone,
		f"Your expense of {_money(doc.currency or 'KES', doc.gross_amount)} "
		f"({doc.vendor_name or 'receipt'}) has been reimbursed.",
	)


def reject_expense(docname, reason=None, approver=None):
	"""Manager rejects a logged expense with a reason. Notifies the sender."""
	doc = frappe.get_doc("Receipt Capture", docname)
	doc.db_set("status", "Rejected")
	doc.db_set("rejection_reason", reason or None)
	doc.db_set("decided_by", approver or frappe.session.user)
	doc.db_set("decided_at", now_datetime())
	frappe.db.commit()
	message = f"Your expense of {_money(doc.currency or 'KES', doc.gross_amount)} " f"({doc.vendor_name or 'receipt'}) was not approved."
	if reason:
		message += f"\nReason: {reason}"
	_safe_send(doc.sender_phone, message)


def confirmation_message(doc):
	currency = doc.currency or "KES"
	lines = [
		"Received your receipt. It is logged and awaiting approval.",
		"",
		f"Vendor: {doc.vendor_name or 'Unknown'}",
		f"Date: {_format_date(doc.receipt_date)}",
		f"Amount: {_money(currency, doc.gross_amount)}",
	]
	if doc.vat_amount not in (None, ""):
		lines.append(f"VAT: {_money(currency, doc.vat_amount)}")
	category = doc.expense_claim_type or doc.suggested_category or "Uncategorised"
	lines.append(f"Category: {category}")

	if doc.validation_errors:
		lines.append("")
		lines.append("Please check:")
		for item in str(doc.validation_errors).splitlines():
			if item.strip():
				lines.append(f"- {item.strip()}")

	lines.append("")
	if doc.needs_claim:
		lines.append("This will be reimbursed to you after a manager approves it.")
	else:
		lines.append("Reply CLAIM if you paid yourself and need reimbursement.")
	lines.append("If the amount is wrong, reply with the correct number.")
	lines.append("Reply NO to withdraw it.")
	return "\n".join(lines)


# ---------------------------------------------------------------------------
# Handle the member's reply
# ---------------------------------------------------------------------------
def handle_reply(phone, text):
	frappe.set_user("Administrator")

	employee = find_employee(phone)
	capture_name = _latest_pending(phone, employee)
	if not capture_name:
		_safe_send(phone, "Send a photo of a receipt to log an expense.")
		return

	doc = frappe.get_doc("Receipt Capture", capture_name)
	settings = frappe.get_cached_doc("UpeoXpense Settings")

	command = (text or "").strip().lower()
	if command in OK_WORDS:
		_confirm(doc)
		return
	if command in NO_WORDS:
		_cancel(doc)
		return
	if command in CLAIM_WORDS:
		_mark_needs_claim(doc)
		return

	amount = _parse_amount(text)
	if amount is not None and amount > 0:
		_correct_amount(doc, amount, settings)
		return

	_safe_send(
		doc.sender_phone,
		confirmation_message(doc)
		+ "\n\nSorry, I did not understand. Reply OK, NO, or a number.",
	)


def _latest_pending(phone, employee):
	filters = {"status": "Awaiting Approval"}
	if employee:
		filters["employee"] = employee
		rows = frappe.get_all(
			"Receipt Capture", filters=filters, order_by="modified desc", limit=1, pluck="name"
		)
		if rows:
			return rows[0]

	# Fall back to matching the sender phone directly.
	variants = phone_variants(phone)
	if variants:
		rows = frappe.get_all(
			"Receipt Capture",
			filters={"status": "Awaiting Approval", "sender_phone": ["in", variants]},
			order_by="modified desc",
			limit=1,
			pluck="name",
		)
		if rows:
			return rows[0]
	return None


def _confirm(doc):
	# The sender acknowledges; a manager still has to approve it.
	frappe.db.commit()
	_safe_send(doc.sender_phone, "Thanks. Your expense is logged and awaiting approval.")


def _cancel(doc):
	# The sender withdraws their own logged expense.
	doc.db_set("status", "Rejected")
	doc.db_set("rejection_reason", "Withdrawn by sender")
	frappe.db.commit()
	_safe_send(doc.sender_phone, "Withdrawn. The receipt is kept on file but will not be approved.")


def _correct_amount(doc, amount, settings):
	doc.db_set("gross_amount", amount)
	errors = validators.validate(
		amount, doc.vat_amount, doc.receipt_date, doc.kra_pin, settings.maximum_receipt_age_days
	)
	doc.db_set("validation_errors", "\n".join(errors) if errors else None)

	doc.reload()
	frappe.db.commit()
	_safe_send(doc.sender_phone, confirmation_message(doc))


# ---------------------------------------------------------------------------
# Retry poller
# ---------------------------------------------------------------------------
def retry_due_extractions():
	"""Re-enqueue extractions whose backoff window has elapsed. Scheduler cron."""
	frappe.set_user("Administrator")
	due = frappe.get_all(
		"Receipt Capture",
		filters={"status": "Extracting", "next_retry_at": ["<=", now_datetime()]},
		pluck="name",
	)
	for name in due:
		# Clear the marker before enqueuing so the poller does not double-fire.
		frappe.db.set_value("Receipt Capture", name, "next_retry_at", None)
		frappe.enqueue("upeo_xpense.pipeline.extract", queue="default", docname=name)
	if due:
		frappe.db.commit()


def _schedule_retry(doc, message):
	count = doc.retry_count or 0
	if count < len(BACKOFF_SECONDS):
		delay = BACKOFF_SECONDS[count]
		doc.db_set("retry_count", count + 1)
		doc.db_set("next_retry_at", add_to_date(now_datetime(), seconds=delay))
		doc.db_set("status", "Extracting")
		doc.db_set("error_message", f"Retry {count + 1} scheduled in {delay}s: {message}"[:1000])
		frappe.db.commit()
	else:
		_fail(doc, f"Could not read after {len(BACKOFF_SECONDS)} attempts: {message}")
		_safe_send(
			doc.sender_phone,
			"We could not read your receipt. Please try again with a clearer photo.",
		)


def _fail(doc, message):
	doc.db_set("status", "Failed")
	doc.db_set("error_message", str(message)[:1000])
	frappe.db.commit()


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _safe_send(phone, message):
	"""Send a WhatsApp text without ever letting a send failure crash the pipeline."""
	try:
		from upeo_xpense import whatsapp

		whatsapp.send_text(phone, message)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "UpeoXpense send_text")


def _parse_amount(text):
	"""Parse a bare number a member may reply with (handles commas, KES prefix)."""
	if text is None:
		return None
	cleaned = str(text).strip()
	cleaned = re.sub(r"(?i)\b(kes|ksh|kshs|sh)\b", "", cleaned)
	cleaned = cleaned.replace(",", "").replace(" ", "")
	if not re.fullmatch(r"\d+(\.\d+)?", cleaned):
		return None
	try:
		return float(cleaned)
	except (ValueError, TypeError):
		return None


def _money(currency, amount):
	if amount in (None, ""):
		return "-"
	try:
		return f"{currency} {float(amount):,.2f}"
	except (ValueError, TypeError):
		return f"{currency} {amount}"


def _format_date(value):
	if not value:
		return "Unknown"
	try:
		return getdate(value).strftime("%d %b %Y")
	except Exception:
		return str(value)


def _clean_str(value):
	if value is None:
		return None
	value = str(value).strip()
	return value or None


def _clean_number(value):
	if value in (None, ""):
		return None
	if isinstance(value, (int, float)):
		return float(value)
	cleaned = re.sub(r"[^\d.\-]", "", str(value))
	if not cleaned:
		return None
	try:
		return float(cleaned)
	except (ValueError, TypeError):
		return None


def _clean_date(value):
	if value in (None, ""):
		return None
	if isinstance(value, date):
		return value.strftime("%Y-%m-%d")
	try:
		return getdate(str(value)[:10]).strftime("%Y-%m-%d")
	except Exception:
		return None
