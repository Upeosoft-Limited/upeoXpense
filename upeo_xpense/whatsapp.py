# Copyright (c) 2026, Upeosoft Limited and contributors
# For license information, please see license.txt

"""All WAClient calls live here, behind two functions:

    send_text(phone, message)
    parse_webhook(payload) -> normalised dict or None

so the provider can be swapped later without touching the pipeline.

WAClient send API (documented at https://waclient.com/docs):
    POST https://waclient.com/api/send
    JSON body: {number, type, message, media_url, filename, instance_id, access_token}

WAClient does NOT publish the shape of the payload it POSTs to an incoming
webhook, and it provides no signature or verification header. So:
  - parse_webhook is deliberately tolerant of several field-name variants and
    logs the raw payload the first time, so the real shape can be confirmed
    against a live message and this parser tightened.
  - the webhook endpoint verifies our own shared `webhook_token` (appended to
    the webhook URL) instead of a provider signature.
"""

import base64
import json

import requests

import frappe

SEND_PATH = "/api/send"
REQUEST_TIMEOUT = 20

# HKDF application-info strings WhatsApp uses to derive media decryption keys.
_MEDIA_HKDF_INFO = {
	"image": b"WhatsApp Image Keys",
	"video": b"WhatsApp Video Keys",
	"audio": b"WhatsApp Audio Keys",
	"document": b"WhatsApp Document Keys",
}


def _settings():
	return frappe.get_cached_doc("UpeoXpense Settings")


# ---------------------------------------------------------------------------
# Sending
# ---------------------------------------------------------------------------
def send_text(phone: str, message: str) -> dict:
	"""Send a plain WhatsApp text message via WAClient."""
	settings = _settings()
	base_url = (settings.waclient_base_url or "https://waclient.com").rstrip("/")
	instance_id = settings.waclient_instance_id
	access_token = settings.get_password("waclient_access_token") if settings.waclient_access_token else None

	if not instance_id or not access_token:
		frappe.throw("WAClient instance id and access token are not configured in UpeoXpense Settings.")

	payload = {
		"number": _clean_number(phone),
		"type": "text",
		"message": message,
		"instance_id": instance_id,
		"access_token": access_token,
	}

	response = requests.post(base_url + SEND_PATH, json=payload, timeout=REQUEST_TIMEOUT)
	response.raise_for_status()
	try:
		return response.json()
	except ValueError:
		return {"raw": response.text}


def _clean_number(phone: str) -> str:
	"""WAClient wants digits only, no +, spaces, or dashes."""
	return "".join(ch for ch in str(phone or "") if ch.isdigit())


# ---------------------------------------------------------------------------
# Receiving
# ---------------------------------------------------------------------------
_SENDER_KEYS = ("from", "sender", "number", "phone", "msisdn", "chat_id", "author", "wa_id")
_TYPE_KEYS = ("type", "message_type", "messageType")
_TEXT_KEYS = ("message", "text", "body", "caption", "conversation")
_MEDIA_KEYS = ("media_url", "mediaUrl", "url", "file", "file_url", "attachment", "media", "image")
_CAPTION_KEYS = ("caption", "text")


def _first(source: dict, keys):
	for key in keys:
		if isinstance(source, dict) and source.get(key) not in (None, ""):
			return source.get(key)
	return None


def _candidate_dicts(payload: dict):
	"""Yield the payload and any nested containers a message might live in."""
	if not isinstance(payload, dict):
		return
	yield payload
	for key in ("data", "message", "payload", "body"):
		nested = payload.get(key)
		if isinstance(nested, dict):
			yield nested
	# Some gateways wrap in a list of messages.
	for key in ("messages", "data"):
		nested = payload.get(key)
		if isinstance(nested, list) and nested and isinstance(nested[0], dict):
			yield nested[0]


def _jid_to_phone(jid):
	"""Extract the digits of a WhatsApp JID (e.g. '254725307131@s.whatsapp.net')."""
	local = str(jid or "").split("@")[0].split(":")[0]
	digits = "".join(ch for ch in local if ch.isdigit())
	return digits if 8 <= len(digits) <= 15 else None


def _pick_sender_jid(key):
	"""Prefer a real phone JID (@s.whatsapp.net / @c.us) over an internal @lid alias."""
	candidates = (
		key.get("remoteJidAlt"),
		key.get("participantAlt"),
		key.get("remoteJid"),
		key.get("participant"),
	)
	for jid in candidates:
		if jid and ("@s.whatsapp.net" in jid or "@c.us" in jid):
			return jid
	return key.get("remoteJidAlt") or key.get("remoteJid")


def _unwrap_message(message):
	"""Peel WhatsApp wrapper envelopes (ephemeral / view-once / edited)."""
	if not isinstance(message, dict):
		return {}
	for wrapper in (
		"ephemeralMessage",
		"viewOnceMessage",
		"viewOnceMessageV2",
		"viewOnceMessageV2Extension",
		"documentWithCaptionMessage",
		"editedMessage",
	):
		inner = message.get(wrapper)
		if isinstance(inner, dict) and isinstance(inner.get("message"), dict):
			return _unwrap_message(inner["message"])
	return message


def _parse_waclient(envelope):
	"""Parse the Baileys 'messages.upsert' event WAClient forwards. Returns the
	normalised dict (with media_key/media_type for encrypted media) or None for
	any event we do not act on (our own messages, receipts, presence, etc.)."""
	if envelope.get("event") != "messages.upsert":
		return None
	messages = (envelope.get("data") or {}).get("messages") or []
	if not messages:
		return None
	msg = messages[0]
	key = msg.get("key") or {}
	if key.get("fromMe"):
		return None
	sender = _jid_to_phone(_pick_sender_jid(key))
	if not sender:
		return None

	message = _unwrap_message(msg.get("message") or {})

	img = message.get("imageMessage") if isinstance(message, dict) else None
	if isinstance(img, dict) and img.get("url"):
		return {
			"sender_phone": sender,
			"message_type": "image",
			"media_url": img.get("url"),
			"media_key": img.get("mediaKey"),
			"media_type": "image",
			"caption": img.get("caption"),
			"text": img.get("caption"),
		}

	doc = message.get("documentMessage") if isinstance(message, dict) else None
	if isinstance(doc, dict) and doc.get("url") and str(doc.get("mimetype", "")).startswith("image/"):
		return {
			"sender_phone": sender,
			"message_type": "image",
			"media_url": doc.get("url"),
			"media_key": doc.get("mediaKey"),
			"media_type": "document",
			"caption": doc.get("caption"),
			"text": doc.get("caption"),
		}

	text = None
	if isinstance(message, dict):
		text = message.get("conversation")
		if not text and isinstance(message.get("extendedTextMessage"), dict):
			text = message["extendedTextMessage"].get("text")
	if text:
		return {
			"sender_phone": sender,
			"message_type": "text",
			"media_url": None,
			"media_key": None,
			"caption": None,
			"text": text,
		}

	return {
		"sender_phone": sender,
		"message_type": "other",
		"media_url": None,
		"media_key": None,
		"caption": None,
		"text": None,
	}


def fetch_media(media_url, media_key=None, media_type="image"):
	"""Download media. If media_key is given (WhatsApp end-to-end encrypted media,
	the '.enc' URLs WAClient forwards), decrypt it to the real bytes."""
	response = requests.get(media_url, timeout=REQUEST_TIMEOUT)
	response.raise_for_status()
	content = response.content
	if not media_key:
		return content
	return _decrypt_media(content, media_key, media_type)


def _decrypt_media(enc, media_key_b64, media_type="image"):
	"""Decrypt WhatsApp media: HKDF-expand the mediaKey, then AES-256-CBC decrypt.
	The '.enc' payload is ciphertext followed by a 10-byte MAC."""
	from cryptography.hazmat.primitives import hashes
	from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
	from cryptography.hazmat.primitives.kdf.hkdf import HKDF

	media_key = base64.b64decode(media_key_b64)
	info = _MEDIA_HKDF_INFO.get(media_type, _MEDIA_HKDF_INFO["image"])
	expanded = HKDF(algorithm=hashes.SHA256(), length=112, salt=None, info=info).derive(media_key)
	iv, cipher_key = expanded[:16], expanded[16:48]
	ciphertext = enc[:-10] if len(enc) > 10 else enc
	decryptor = Cipher(algorithms.AES(cipher_key), modes.CBC(iv)).decryptor()
	plain = decryptor.update(ciphertext) + decryptor.finalize()
	if plain:  # strip PKCS7 padding
		pad = plain[-1]
		if 1 <= pad <= 16:
			plain = plain[:-pad]
	return plain


def parse_webhook(payload) -> dict | None:
	"""Normalise an incoming WAClient webhook payload.

	Returns a dict:
	    {"sender_phone", "message_type" ("image"|"text"|"other"), "text",
	     "media_url", "caption"}
	or None if no sender phone could be found (nothing we can act on).
	"""
	if isinstance(payload, (str, bytes)):
		try:
			payload = json.loads(payload)
		except (ValueError, TypeError):
			return None
	if not isinstance(payload, dict):
		return None

	# WAClient forwards raw Baileys events:
	#   {"instance_id": "...", "data": {"event": "messages.upsert",
	#                                    "data": {"messages": [ {key, message, ...} ]}}}
	envelope = payload.get("data")
	if isinstance(envelope, dict) and "event" in envelope:
		return _parse_waclient(envelope)

	sender = None
	raw_type = None
	text = None
	media = None
	caption = None

	for source in _candidate_dicts(payload):
		sender = sender or _first(source, _SENDER_KEYS)
		raw_type = raw_type or _first(source, _TYPE_KEYS)
		text = text or _first(source, _TEXT_KEYS)
		media = media or _first(source, _MEDIA_KEYS)
		caption = caption or _first(source, _CAPTION_KEYS)

	# A media value may itself be a dict like {"url": "...", "caption": "..."}.
	if isinstance(media, dict):
		caption = caption or _first(media, _CAPTION_KEYS)
		media = _first(media, ("url", "link", "file_url", "media_url", "href"))

	if not sender:
		return None

	raw_type = (str(raw_type).lower() if raw_type else "")
	if media:
		message_type = "image"
	elif raw_type in ("text", "chat", "conversation"):
		message_type = "text"
	elif raw_type in ("image", "media", "photo", "document"):
		# Type says media but we found no url; treat as other so we can reply.
		message_type = "other"
	elif text:
		message_type = "text"
	else:
		message_type = "other"

	return {
		"sender_phone": str(sender),
		"message_type": message_type,
		"text": (str(text) if text is not None else None),
		"media_url": (str(media) if media else None),
		"caption": (str(caption) if caption else None),
	}


# ---------------------------------------------------------------------------
# Webhook endpoint
# ---------------------------------------------------------------------------
@frappe.whitelist(allow_guest=True)
def webhook(**kwargs):
	"""WAClient posts here. Verify our token, return 200 immediately, and do the
	real work in a background job. Never do slow work in the webhook handler."""
	# Read the raw body so we can log and parse the provider's exact shape.
	raw = None
	try:
		if frappe.request and frappe.request.data:
			raw = frappe.request.data.decode("utf-8", errors="replace")
	except Exception:
		raw = None

	payload = None
	if raw:
		try:
			payload = json.loads(raw)
		except (ValueError, TypeError):
			payload = None
	if payload is None:
		# Fall back to form-encoded params.
		payload = {k: v for k, v in (kwargs or {}).items() if k not in ("cmd",)}

	# Verify our shared token (WAClient sends no signature of its own).
	settings = _settings()
	expected = settings.webhook_token
	if expected:
		# WAClient appends the token to the URL query string; frappe.form_dict does
		# not always carry query params on a JSON POST, so read request.args first.
		provided = None
		if frappe.request:
			provided = frappe.request.args.get("webhook_token") or frappe.request.args.get("token")
		provided = (
			provided
			or frappe.form_dict.get("webhook_token")
			or frappe.form_dict.get("token")
			or (payload.get("webhook_token") if isinstance(payload, dict) else None)
			or (payload.get("token") if isinstance(payload, dict) else None)
		)
		if provided != expected:
			frappe.local.response["http_status_code"] = 401
			return {"status": "unauthorized"}

	# Log the raw payload so the provider shape can be inspected if needed.
	frappe.logger("upeo_xpense").warning({"event": "waclient_webhook", "payload": payload})

	# Hand off to a background job and return 200 right away.
	frappe.enqueue(
		"upeo_xpense.pipeline.handle_incoming",
		queue="default",
		payload=payload,
	)
	return {"status": "ok"}
