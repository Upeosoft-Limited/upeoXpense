# Copyright (c) 2026, Upeosoft Limited and contributors
# For license information, please see license.txt

import types
import unittest
from unittest.mock import patch

from upeo_xpense import pipeline, whatsapp


class TestPhoneNormalisation(unittest.TestCase):
	def test_variants_from_local_format(self):
		variants = set(pipeline.phone_variants("0712345678"))
		self.assertIn("254712345678", variants)
		self.assertIn("0712345678", variants)
		self.assertIn("712345678", variants)

	def test_variants_from_international(self):
		variants = set(pipeline.phone_variants("+254 712 345 678"))
		self.assertIn("254712345678", variants)
		self.assertIn("0712345678", variants)

	def test_variants_intersect_across_formats(self):
		a = set(pipeline.phone_variants("+254712345678"))
		b = set(pipeline.phone_variants("0712345678"))
		self.assertTrue(a & b)

	def test_empty(self):
		self.assertEqual(pipeline.phone_variants("abc"), [])


class TestAmountParsing(unittest.TestCase):
	def test_plain_number(self):
		self.assertEqual(pipeline._parse_amount("1450"), 1450.0)

	def test_with_commas(self):
		self.assertEqual(pipeline._parse_amount("1,450.50"), 1450.5)

	def test_with_currency_prefix(self):
		self.assertEqual(pipeline._parse_amount("KES 1450"), 1450.0)

	def test_non_number(self):
		self.assertIsNone(pipeline._parse_amount("ok"))

	def test_word_no(self):
		self.assertIsNone(pipeline._parse_amount("no"))


class TestWebhookParsing(unittest.TestCase):
	def test_text_message_variant_a(self):
		parsed = whatsapp.parse_webhook({"from": "254712345678", "type": "text", "message": "OK"})
		self.assertEqual(parsed["sender_phone"], "254712345678")
		self.assertEqual(parsed["message_type"], "text")
		self.assertEqual(parsed["text"], "OK")

	def test_media_message_variant_a(self):
		parsed = whatsapp.parse_webhook(
			{"from": "254712345678", "type": "media", "media_url": "https://x/y.jpg", "caption": "lunch"}
		)
		self.assertEqual(parsed["message_type"], "image")
		self.assertEqual(parsed["media_url"], "https://x/y.jpg")
		self.assertEqual(parsed["caption"], "lunch")

	def test_nested_data_wrapper(self):
		parsed = whatsapp.parse_webhook(
			{"event": "message", "data": {"sender": "0712345678", "type": "image", "url": "https://x/y.png"}}
		)
		self.assertEqual(parsed["sender_phone"], "0712345678")
		self.assertEqual(parsed["message_type"], "image")
		self.assertEqual(parsed["media_url"], "https://x/y.png")

	def test_media_as_dict(self):
		parsed = whatsapp.parse_webhook(
			{"from": "254712345678", "type": "image", "media": {"url": "https://x/z.jpg", "caption": "taxi"}}
		)
		self.assertEqual(parsed["media_url"], "https://x/z.jpg")
		self.assertEqual(parsed["caption"], "taxi")

	def test_no_sender_returns_none(self):
		self.assertIsNone(whatsapp.parse_webhook({"type": "text", "message": "hi"}))

	def test_json_string_payload(self):
		parsed = whatsapp.parse_webhook('{"from": "254712345678", "type": "text", "text": "yes"}')
		self.assertEqual(parsed["sender_phone"], "254712345678")


class TestJsonParsing(unittest.TestCase):
	def test_plain_json(self):
		self.assertEqual(pipeline._parse_json('{"a": 1}'), {"a": 1})

	def test_json_with_prose(self):
		self.assertEqual(pipeline._parse_json('Here you go:\n{"a": 1}\nThanks'), {"a": 1})

	def test_garbage(self):
		self.assertIsNone(pipeline._parse_json("not json"))


class TestNeedsRetry(unittest.TestCase):
	def test_none_needs_retry(self):
		self.assertTrue(pipeline._needs_retry(None, 0.7))

	def test_low_confidence_needs_retry(self):
		self.assertTrue(
			pipeline._needs_retry(
				{"confidence": 0.4, "gross_amount": 10, "receipt_date": "2026-07-19"}, 0.7
			)
		)

	def test_missing_required_needs_retry(self):
		self.assertTrue(
			pipeline._needs_retry({"confidence": 0.95, "gross_amount": None, "receipt_date": None}, 0.7)
		)

	def test_confident_and_complete_no_retry(self):
		self.assertFalse(
			pipeline._needs_retry(
				{"confidence": 0.95, "gross_amount": 10, "receipt_date": "2026-07-19"}, 0.7
			)
		)


class TestExtractWithModels(unittest.TestCase):
	def _fake_settings(self):
		fake = types.SimpleNamespace(anthropic_api_key="sk-test")
		fake.get_password = lambda field: "sk-test"
		return fake

	def test_retries_with_stronger_model_on_low_confidence(self):
		low = ({"confidence": 0.3, "gross_amount": 10, "receipt_date": "2026-07-19"}, "raw-low")
		high = ({"confidence": 0.95, "gross_amount": 10, "receipt_date": "2026-07-19"}, "raw-high")
		with patch.object(pipeline, "_call_claude", side_effect=[low, high]) as call:
			result, raw = pipeline._extract_with_models("b64", self._fake_settings(), 0.7)
		self.assertEqual(call.call_count, 2)
		self.assertEqual(result["confidence"], 0.95)
		self.assertEqual(raw, "raw-high")
		# First call uses the fast model, second uses the strong one.
		self.assertEqual(call.call_args_list[0].args[0], pipeline.MODEL_FIRST)
		self.assertEqual(call.call_args_list[1].args[0], pipeline.MODEL_RETRY)

	def test_no_retry_when_confident(self):
		good = ({"confidence": 0.9, "gross_amount": 10, "receipt_date": "2026-07-19"}, "raw-good")
		with patch.object(pipeline, "_call_claude", side_effect=[good]) as call:
			result, raw = pipeline._extract_with_models("b64", self._fake_settings(), 0.7)
		self.assertEqual(call.call_count, 1)
		self.assertEqual(raw, "raw-good")


if __name__ == "__main__":
	unittest.main()
