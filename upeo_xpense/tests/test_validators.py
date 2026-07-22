# Copyright (c) 2026, Upeosoft Limited and contributors
# For license information, please see license.txt

import unittest
from datetime import date, timedelta

from upeo_xpense import validators


class TestValidators(unittest.TestCase):
	def setUp(self):
		self.today = date(2026, 7, 21)

	def test_clean_receipt_passes(self):
		errors = validators.validate(
			gross_amount=1450.0,
			vat_amount=200.0,
			receipt_date="2026-07-19",
			kra_pin="P051234567X",
			max_age_days=90,
			today=self.today,
		)
		self.assertEqual(errors, [])

	def test_zero_amount_flagged(self):
		errors = validators.validate(0, None, "2026-07-19", None, 90, today=self.today)
		self.assertTrue(any("above zero" in e for e in errors))

	def test_missing_amount_flagged(self):
		errors = validators.validate(None, None, "2026-07-19", None, 90, today=self.today)
		self.assertTrue(any("Amount could not be read" in e for e in errors))

	def test_vat_within_tolerance_ok(self):
		# 16% VAT-inclusive on 1450 => ~200.0
		errors = validators.validate(1450.0, 200.0, "2026-07-19", None, 90, today=self.today)
		self.assertFalse(any("VAT" in e for e in errors))

	def test_vat_out_of_tolerance_flagged(self):
		errors = validators.validate(1450.0, 500.0, "2026-07-19", None, 90, today=self.today)
		self.assertTrue(any("VAT" in e for e in errors))

	def test_null_vat_is_fine(self):
		errors = validators.validate(1450.0, None, "2026-07-19", None, 90, today=self.today)
		self.assertFalse(any("VAT" in e for e in errors))

	def test_future_date_flagged(self):
		future = (self.today + timedelta(days=3)).isoformat()
		errors = validators.validate(100.0, None, future, None, 90, today=self.today)
		self.assertTrue(any("future" in e for e in errors))

	def test_too_old_flagged(self):
		old = (self.today - timedelta(days=200)).isoformat()
		errors = validators.validate(100.0, None, old, None, 90, today=self.today)
		self.assertTrue(any("older than" in e for e in errors))

	def test_bad_kra_pin_flagged(self):
		errors = validators.validate(100.0, None, "2026-07-19", "123456", 90, today=self.today)
		self.assertTrue(any("KRA PIN" in e for e in errors))

	def test_good_kra_pin_ok(self):
		errors = validators.validate(100.0, None, "2026-07-19", "A012345678Z", 90, today=self.today)
		self.assertFalse(any("KRA PIN" in e for e in errors))


if __name__ == "__main__":
	unittest.main()
