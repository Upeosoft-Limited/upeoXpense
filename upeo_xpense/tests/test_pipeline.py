# Copyright (c) 2026, Upeosoft Limited and contributors
# For license information, please see license.txt

"""End-to-end pipeline test with the WhatsApp send and the Claude call mocked.

Guarded: if the site has no Company (ERPNext not set up), the test skips rather
than failing, since Employee and Expense Claim need a Company.
"""

import io
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from upeo_xpense import pipeline

PHONE = "254700111222"
GOOD_EXTRACT = {
	"vendor_name": "Java House",
	"receipt_date": "2026-07-19",
	"currency": "KES",
	"gross_amount": 1450.0,
	"vat_amount": 200.0,
	"kra_pin": "P051234567X",
	"etims_invoice_number": "0100001234",
	"payment_method": "Card",
	"line_items": [{"description": "Lunch", "amount": 1450.0}],
	"suggested_category": "Meals and Entertainment",
	"confidence": 0.95,
}


def _tiny_jpeg():
	from PIL import Image

	buffer = io.BytesIO()
	Image.new("RGB", (32, 32), (240, 240, 240)).save(buffer, "JPEG")
	return buffer.getvalue()


class TestPipelineEndToEnd(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = frappe.db.get_value("Company", {}, "name")
		# hrms validate() commits mid-transaction, which defeats FrappeTestCase's
		# rollback and would leave our test WAClient values in the real Single.
		# Snapshot the credentials so tearDownClass can put them back.
		settings = frappe.get_single("UpeoXpense Settings")
		cls._saved_settings = {
			"waclient_base_url": settings.waclient_base_url,
			"waclient_instance_id": settings.waclient_instance_id,
			"waclient_access_token": settings.get_password("waclient_access_token")
			if settings.waclient_access_token
			else None,
			"anthropic_api_key": settings.get_password("anthropic_api_key")
			if settings.anthropic_api_key
			else None,
			"default_company": settings.default_company,
			"default_expense_claim_type": settings.default_expense_claim_type,
			"minimum_confidence": settings.minimum_confidence,
			"maximum_receipt_age_days": settings.maximum_receipt_age_days,
		}

	@classmethod
	def tearDownClass(cls):
		# hrms validate() commits mid-transaction, so records this suite creates
		# survive FrappeTestCase rollback. Delete them explicitly to leave the
		# site as we found it.
		try:
			for rc in frappe.get_all("Receipt Capture", filters={"sender_phone": PHONE}, pluck="name"):
				frappe.db.set_value("Receipt Capture", rc, "expense_claim", None)
				frappe.delete_doc("Receipt Capture", rc, force=1, ignore_permissions=True)
			test_emp = frappe.db.get_value("Employee", {"cell_number": PHONE}, "name")
			if test_emp:
				for c in frappe.get_all("Expense Claim", filters={"employee": test_emp}, pluck="name"):
					claim = frappe.get_doc("Expense Claim", c)
					if claim.docstatus == 1:
						claim.cancel()
					frappe.delete_doc("Expense Claim", c, force=1, ignore_permissions=True)
				frappe.delete_doc("Employee", test_emp, force=1, ignore_permissions=True)
			if frappe.db.exists("Expense Claim Type", "UpeoXpense Test Type"):
				frappe.delete_doc(
					"Expense Claim Type", "UpeoXpense Test Type", force=1, ignore_permissions=True
				)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "UpeoXpense test cleanup")

		saved = getattr(cls, "_saved_settings", None)
		if saved is not None:
			settings = frappe.get_single("UpeoXpense Settings")
			for field, value in saved.items():
				settings.set(field, value)
			settings.save(ignore_permissions=True)
		frappe.db.commit()
		super().tearDownClass()

	def setUp(self):
		if not self.company:
			self.skipTest("No Company on this site; ERPNext not set up.")

		# Expense Claim Type with a default account for the company (hrms needs it
		# even to save a draft claim).
		expense_account = frappe.db.get_value(
			"Account",
			{"company": self.company, "root_type": "Expense", "is_group": 0},
			"name",
		)
		if not expense_account:
			self.skipTest("No leaf Expense account for the company.")

		self.ect = "UpeoXpense Test Type"
		if frappe.db.exists("Expense Claim Type", self.ect):
			ect_doc = frappe.get_doc("Expense Claim Type", self.ect)
		else:
			ect_doc = frappe.get_doc({"doctype": "Expense Claim Type", "expense_type": self.ect})
		if not any(row.company == self.company for row in ect_doc.accounts):
			ect_doc.append("accounts", {"company": self.company, "default_account": expense_account})
		ect_doc.save(ignore_permissions=True)

		# Employee
		self.employee = frappe.db.get_value("Employee", {"cell_number": PHONE}, "name")
		if not self.employee:
			try:
				emp = frappe.get_doc(
					{
						"doctype": "Employee",
						"employee_name": "UpeoXpense Tester",
						"first_name": "UpeoXpense",
						"last_name": "Tester",
						"company": self.company,
						"cell_number": PHONE,
						"status": "Active",
						"gender": "Other",
						"date_of_birth": "1990-01-01",
						"date_of_joining": "2020-01-01",
					}
				).insert(ignore_permissions=True)
				self.employee = emp.name
			except Exception as exc:
				self.skipTest(f"Could not create test Employee: {exc}")

		# Settings
		settings = frappe.get_single("UpeoXpense Settings")
		settings.anthropic_api_key = "sk-test"
		settings.waclient_instance_id = "TEST"
		settings.waclient_access_token = "TEST"
		settings.minimum_confidence = 0.7
		settings.maximum_receipt_age_days = 90
		settings.default_company = self.company
		settings.default_expense_claim_type = self.ect
		settings.save(ignore_permissions=True)

	def _make_capture(self, file_hash):
		doc = frappe.new_doc("Receipt Capture")
		doc.employee = self.employee
		doc.sender_phone = PHONE
		doc.status = "Queued"
		doc.file_hash = file_hash
		doc.insert(ignore_permissions=True)
		pipeline._attach(doc, "receipt.jpg", _tiny_jpeg(), df="receipt_file")
		doc.reload()
		return doc

	def test_extract_creates_draft_and_confirms(self):
		doc = self._make_capture("hash-extract-1")
		with patch.object(pipeline, "_call_claude", return_value=(GOOD_EXTRACT, "raw")), patch(
			"upeo_xpense.whatsapp.send_text"
		) as send:
			pipeline.extract(doc.name)

		doc.reload()
		self.assertEqual(doc.status, "Awaiting Confirmation")
		self.assertTrue(doc.expense_claim)
		self.assertEqual(float(doc.gross_amount), 1450.0)
		self.assertEqual(doc.vendor_name, "Java House")
		self.assertTrue(doc.raw_extract)

		claim = frappe.get_doc("Expense Claim", doc.expense_claim)
		self.assertEqual(claim.docstatus, 0)
		self.assertEqual(float(claim.expenses[0].amount), 1450.0)

		# WhatsApp confirmation was sent.
		self.assertTrue(send.called)
		message = send.call_args.args[1]
		self.assertIn("Received your receipt", message)
		self.assertIn("Java House", message)

	def test_reply_ok_confirms(self):
		doc = self._make_capture("hash-ok-1")
		with patch.object(pipeline, "_call_claude", return_value=(GOOD_EXTRACT, "raw")), patch(
			"upeo_xpense.whatsapp.send_text"
		):
			pipeline.extract(doc.name)

		with patch("upeo_xpense.whatsapp.send_text") as send:
			pipeline.handle_reply(PHONE, "OK")

		doc.reload()
		self.assertEqual(doc.status, "Confirmed")
		self.assertTrue(send.called)

	def test_reply_no_cancels(self):
		doc = self._make_capture("hash-no-1")
		with patch.object(pipeline, "_call_claude", return_value=(GOOD_EXTRACT, "raw")), patch(
			"upeo_xpense.whatsapp.send_text"
		):
			pipeline.extract(doc.name)
		claim_name = frappe.db.get_value("Receipt Capture", doc.name, "expense_claim")

		with patch("upeo_xpense.whatsapp.send_text") as send:
			pipeline.handle_reply(PHONE, "NO")

		doc.reload()
		self.assertEqual(doc.status, "Rejected")
		self.assertFalse(doc.expense_claim)
		self.assertFalse(frappe.db.exists("Expense Claim", claim_name))
		self.assertTrue(send.called)

	def test_reply_number_corrects_amount(self):
		doc = self._make_capture("hash-num-1")
		with patch.object(pipeline, "_call_claude", return_value=(GOOD_EXTRACT, "raw")), patch(
			"upeo_xpense.whatsapp.send_text"
		):
			pipeline.extract(doc.name)

		with patch("upeo_xpense.whatsapp.send_text") as send:
			pipeline.handle_reply(PHONE, "2000")

		doc.reload()
		self.assertEqual(float(doc.gross_amount), 2000.0)
		claim = frappe.get_doc("Expense Claim", doc.expense_claim)
		self.assertEqual(float(claim.expenses[0].amount), 2000.0)
		self.assertTrue(send.called)
		self.assertIn("2,000.00", send.call_args.args[1])

	def test_duplicate_is_marked(self):
		content = _tiny_jpeg()
		import hashlib

		file_hash = hashlib.sha256(content).hexdigest()
		original = self._make_capture(file_hash)

		with patch("requests.get") as get, patch("upeo_xpense.whatsapp.send_text") as send:
			get.return_value.content = content
			get.return_value.raise_for_status = lambda: None
			pipeline.ingest(PHONE, "https://example.com/receipt.jpg", caption="again")

		# A Duplicate record was created and the member was told.
		dupes = frappe.get_all(
			"Receipt Capture", filters={"duplicate_of": original.name, "status": "Duplicate"}
		)
		self.assertTrue(dupes)
		self.assertTrue(send.called)
		self.assertIn("already have this receipt", send.call_args.args[1])
