# Copyright (c) 2026, Upeosoft Limited and contributors
# For license information, please see license.txt

"""Plain-Python validation of an extracted receipt. No AI here.

Claude returns data with a confidence score. Python decides what happens next.
These checks never block the pipeline; they only produce human-readable warnings
that get shown to the member in the confirmation message so they can correct.
"""

import re
from datetime import date, datetime

KRA_PIN_RE = re.compile(r"^[A-Z]\d{9}[A-Z]$")

# Kenya VAT rate. Receipts print VAT-inclusive totals.
VAT_RATE = 0.16
# Allowable slack when checking the printed VAT against a 16% computation.
VAT_TOLERANCE = 1.0


def _to_date(value):
	"""Coerce a value to a datetime.date, or None."""
	if value is None or value == "":
		return None
	if isinstance(value, datetime):
		return value.date()
	if isinstance(value, date):
		return value
	try:
		return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
	except (ValueError, TypeError):
		return None


def validate(
	gross_amount,
	vat_amount,
	receipt_date,
	kra_pin,
	max_age_days,
	today=None,
):
	"""Return a list of human-readable validation error strings (possibly empty).

	- Gross amount above zero.
	- VAT plausible against a 16 percent computation, within 1 unit, or null.
	- Date not in the future, not older than the configured window.
	- KRA PIN matches ^[A-Z]\\d{9}[A-Z]$ if present.
	"""
	errors = []
	today = today or date.today()

	# Gross amount above zero.
	if gross_amount is None:
		errors.append("Amount could not be read.")
	else:
		try:
			gross = float(gross_amount)
		except (ValueError, TypeError):
			gross = None
			errors.append("Amount is not a number.")
		if gross is not None and gross <= 0:
			errors.append("Amount is not above zero.")

	# VAT plausible against a 16 percent computation, within 1 unit, or null.
	if vat_amount is not None and vat_amount != "" and gross_amount is not None:
		try:
			gross = float(gross_amount)
			vat = float(vat_amount)
			# Total is VAT inclusive: vat = gross * rate / (1 + rate).
			expected_vat = gross * VAT_RATE / (1 + VAT_RATE)
			if abs(vat - expected_vat) > VAT_TOLERANCE:
				errors.append(
					f"VAT {vat:.2f} does not match a 16% computation "
					f"(expected about {expected_vat:.2f})."
				)
		except (ValueError, TypeError):
			errors.append("VAT is not a number.")

	# Date not in the future, not older than the configured window.
	parsed_date = _to_date(receipt_date)
	if receipt_date in (None, ""):
		errors.append("Date could not be read.")
	elif parsed_date is None:
		errors.append("Date is not a valid date.")
	else:
		if parsed_date > today:
			errors.append("Date is in the future.")
		elif max_age_days and (today - parsed_date).days > int(max_age_days):
			errors.append(f"Receipt is older than {int(max_age_days)} days.")

	# KRA PIN matches the pattern if present.
	if kra_pin:
		if not KRA_PIN_RE.match(str(kra_pin).strip().upper()):
			errors.append("KRA PIN does not look valid.")

	return errors
