# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""The Support chat (TBO Copilot Phase 5): this site relays its user's messages to TBO Support.

Each message goes server to server to the hub's `helpdesk.api.copilot_conversation.message`,
signed with a key derived from the pairing key both sites already hold, so the browser never
talks to the hub and the hub knows which site vouches for the user. The hub answers in the same
call; what it starts later (progress, the team's replies) arrives through `hub_api.post_message`.
This is the site's third call to the hub, after pairing and the new-ticket ping.
"""

import hashlib
import hmac
import json
import secrets
import time

import frappe
import requests
from frappe import _
from frappe.utils import now_datetime

from helpdesk_client import inbox
from helpdesk_client.utils.context import raiser_identity, ticket_context

CONVERSATION, MESSAGE = "Support Conversation", "Support Conversation Message"
ENDPOINT = "/api/method/helpdesk.api.copilot_conversation.message"
SIGNING_CONTEXT = b"conversation-v1"
RELAY_TIMEOUT = 60
MAX_TEXT = 4000


class ChatUnavailable(frappe.ValidationError):
	"""The chat cannot reach TBO Support now: the panel offers the form instead."""


def _settings():
	return frappe.get_cached_doc("HDS Support Settings")


def chat_enabled() -> bool:
	settings = _settings()
	return bool(settings.enable_ticket_raising and settings.get("enable_chat") and settings.client_id)


def _require_chat():
	inbox.require_user()
	if not chat_enabled():
		raise ChatUnavailable(_("The support chat is not available; please use the form."))


def signing_key(approval_key: str) -> bytes:
	"""The key this site signs its chat with: derived from the pairing key, used for nothing else."""
	return hmac.new(approval_key.encode(), SIGNING_CONTEXT, hashlib.sha256).digest()


def _relay(payload: dict) -> dict:
	"""One signed message to TBO Support; its answer."""
	settings = _settings()
	key = settings.get_password("approval_key", raise_exception=False)
	if not (key and settings.client_id and settings.qcs_hub_url):
		raise ChatUnavailable(_("This site is not connected to TBO Support."))
	body = json.dumps(payload, default=str).encode()
	timestamp, nonce = str(int(time.time())), secrets.token_hex(16)
	signature = hmac.new(
		signing_key(key), f"{timestamp}.{nonce}.".encode() + body, hashlib.sha256
	).hexdigest()
	try:
		response = requests.post(
			settings.qcs_hub_url.rstrip("/") + ENDPOINT,
			data=body,
			headers={
				"Content-Type": "application/json",
				"X-TBO-Connection": settings.client_id,
				"X-TBO-Timestamp": timestamp,
				"X-TBO-Nonce": nonce,
				"X-TBO-Signature": signature,
			},
			timeout=RELAY_TIMEOUT,
		)
	except requests.RequestException as e:
		raise ChatUnavailable(_("TBO Support could not be reached; please use the form.")) from e
	if response.status_code != 200:
		raise ChatUnavailable(_("TBO Support could not take the message; please use the form."))
	try:
		return response.json()
	except ValueError as e:
		raise ChatUnavailable(_("TBO Support's answer could not be read.")) from e


def _user() -> dict:
	email, name = raiser_identity(frappe.session.user, _settings().fallback_contact_email)
	language = frappe.db.get_value("User", frappe.session.user, "language") or frappe.local.lang or "en"
	return {"email": email, "name": name, "language": language}


def _mine(conversation: str):
	doc = frappe.get_doc(CONVERSATION, conversation)
	if doc.user != frappe.session.user:
		frappe.throw(_("This is not your conversation."), frappe.PermissionError)
	return doc


def _keep(doc, reply: dict) -> list[dict]:
	"""The hub's messages, kept here; the conversation follows its state."""
	kept = []
	for message in reply.get("messages") or []:
		row = _add(doc, message)
		if row:
			kept.append(_as_dict(row))
	values = {"last_message_at": now_datetime()}
	if reply.get("conversation"):
		values["hub_conversation"] = reply["conversation"]
	if reply.get("state"):
		values["status"] = reply["state"]
	if reply.get("language"):
		values["language"] = reply["language"]
	doc.db_set(values, update_modified=False)
	return kept


def _add(doc, message: dict, hub_ref: str | None = None):
	hub_ref = hub_ref or message.get("name")
	if hub_ref and frappe.db.exists(MESSAGE, {"conversation": doc.name, "hub_ref": hub_ref}):
		return None
	card = message.get("card")
	return frappe.get_doc(
		{
			"doctype": MESSAGE,
			"conversation": doc.name,
			"direction": message.get("direction") or "Assistant",
			"kind": str(message.get("kind") or "Text")[:40],
			"text": str(message.get("text") or "")[: MAX_TEXT * 2],
			"card": card if isinstance(card, str) else json.dumps(card) if card else None,
			"hub_ref": hub_ref,
		}
	).insert(ignore_permissions=True)


def _as_dict(row) -> dict:
	return {
		"name": row.name,
		"direction": row.direction,
		"kind": row.kind,
		"text": row.text,
		"card": frappe.parse_json(row.card) if row.card else None,
		"files": frappe.parse_json(row.files) if row.files else [],
		"creation": str(row.creation),
	}


@frappe.whitelist(methods=["POST"])
def start(page_route: str = "", ref_doctype: str = "", ref_docname: str = "", new: int = 0) -> dict:
	"""The user's open chat (its messages), or a new one with the assistant's greeting.

	A ticket's chat is never resumed here: it opens from the ticket (`open_ticket`)."""
	_require_chat()
	if not int(new or 0):
		open_name = frappe.db.get_value(
			CONVERSATION,
			{
				"user": frappe.session.user,
				"status": ["in", inbox.OPEN_CHAT_STATES],
				"ticket": ["is", "not set"],
			},
			"name",
			order_by="creation desc",
		)
		if open_name:
			return history(open_name)
	doc = frappe.get_doc({"doctype": CONVERSATION, "user": frappe.session.user, "status": "Talking"}).insert(
		ignore_permissions=True
	)
	context = ticket_context(_settings(), page_route, ref_doctype, ref_docname)
	reply = _relay(
		{
			"action": "start",
			"client_conversation": doc.name,
			"user": _user(),
			"context": {
				key: context[key]
				for key in (
					"page_route",
					"ref_doctype",
					"ref_docname",
					"user_roles",
					"error_logs",
					"code_identity",
				)
			},
		}
	)
	if not reply.get("enabled"):
		frappe.delete_doc(CONVERSATION, doc.name, ignore_permissions=True, force=True)
		raise ChatUnavailable(_("The support chat is not available; please use the form."))
	_keep(doc, reply)
	return history(doc.name)


@frappe.whitelist(methods=["GET", "POST"])
def history(conversation: str) -> dict:
	doc = _mine(conversation)
	rows = frappe.get_all(
		MESSAGE,
		filters={"conversation": doc.name},
		fields=["name", "direction", "kind", "text", "card", "files", "creation"],
		order_by="creation asc",
	)
	return {
		"conversation": doc.name,
		"status": doc.status,
		"ticket": doc.ticket,
		"ticket_state": inbox.ticket_card(frappe.get_doc(inbox.TICKET, doc.ticket)) if doc.ticket else None,
		"messages": [_as_dict(frappe._dict(r)) for r in rows],
	}


@frappe.whitelist(methods=["POST"])
def open_ticket(ticket: str) -> dict:
	"""A ticket's chat. One raised with the form gets its chat the first time it is opened (Phase 13):
	its text and the team's updates first, then TBO Support links the chat to the ticket."""
	inbox.require_user()
	t = inbox.my_ticket(ticket)
	name = frappe.db.get_value(CONVERSATION, {"ticket": t.name}, "name")
	if name:
		return history(name)
	if not (chat_enabled() and t.ticket_id):
		# TBO Support has not picked it up yet, or this site has no chat: its story, read-only
		return _read_only(t)
	doc = frappe.get_doc(
		{"doctype": CONVERSATION, "user": frappe.session.user, "status": "With a person", "ticket": t.name}
	).insert(ignore_permissions=True)
	try:
		reply = _relay(
			{
				"action": "open_ticket",
				"client_conversation": doc.name,
				"client_ticket": t.name,
				"user": _user(),
			}
		)
	except ChatUnavailable:
		# an older TBO Support, or none reachable: try again next time
		frappe.delete_doc(CONVERSATION, doc.name, ignore_permissions=True, force=True)
		return _read_only(t)
	for message in _ticket_story(t):
		_add(doc, message)
	_keep(doc, reply)
	return history(doc.name)


def _ticket_story(t) -> list[dict]:
	"""A form ticket's text and TBO Support's updates on it, as the first messages of its chat."""
	from frappe.core.utils import html2text

	story = []
	text = html2text(t.description or "", wrap=False).strip()
	if text or t.subject:
		story.append({"direction": "Customer", "kind": "Text", "text": text or t.subject})
	for u in sorted(t.updates or [], key=lambda u: str(u.posted_at or "")):
		if u.kind == "Reply":
			author = u.author_name or _("TBO Support")
			story.append(
				{
					"direction": "Agent",
					"kind": "Text",
					"text": u.message,
					"card": {"title": author, "lines": [u.message]},
				}
			)
		elif u.kind == "Stage":
			story.append(
				{
					"direction": "System",
					"kind": "Stage",
					"text": u.message or _(u.stage),
					"card": {"title": _(u.stage), "lines": [u.message] if u.message else []},
				}
			)
		elif u.message:
			story.append({"direction": "System", "kind": "Text", "text": u.message})
	return story


def _read_only(t) -> dict:
	return {
		"conversation": None,
		"status": None,
		"ticket": t.name,
		"ticket_state": inbox.ticket_card(t),
		"read_only": True,
		"note": _("The chat for this ticket opens once TBO Support has picked it up.")
		if not t.ticket_id
		else _("The chat is not available right now."),
		"messages": [
			{"name": None, "files": [], "creation": None, "card": None, **m} for m in _ticket_story(t)
		],
	}


@frappe.whitelist(methods=["POST"])
def send(
	conversation: str, text: str = "", action: str = "", files: str | list | None = None, note: str = ""
) -> dict:
	"""The user's message or button press: it goes to TBO Support, and its answer comes back."""
	_require_chat()
	doc = _mine(conversation)
	if doc.ticket and action in ("fixed", "still_broken"):
		return _answer_the_fix(doc, action == "fixed", note)
	if doc.ticket and inbox.ticket_card(frappe.get_doc(inbox.TICKET, doc.ticket))["closed"] and not action:
		frappe.throw(
			_("This ticket is closed. Press It came back if the problem is back, or start a new chat.")
		)
	text = (text or "").strip()[:MAX_TEXT]
	files = _own_files(files)
	if text or files:
		frappe.get_doc(
			{
				"doctype": MESSAGE,
				"conversation": doc.name,
				"direction": "Customer",
				"kind": "Text",
				"text": text,
				"files": json.dumps(files) if files else None,
			}
		).insert(ignore_permissions=True)
	reply = _relay(
		{
			"conversation": doc.hub_conversation,
			"client_conversation": doc.name,
			"user": _user(),
			"text": text,
			"action": action,
			"note": (note or "").strip()[:1000],
			"files": files,
		}
	)
	kept = _keep(doc, reply)
	doc.reload()
	if reply.get("ticket") and not doc.ticket:
		_ticket_for(doc, reply)
	return {"conversation": doc.name, "status": doc.status, "ticket": doc.ticket, "messages": kept}


def _answer_the_fix(doc, fixed: bool, note: str) -> dict:
	"""It's fixed / Still broken / It came back in a ticket's chat: recorded on the ticket here, as on its
	form, so the dot changes at once and TBO Support applies it once on its next sync."""
	from helpdesk_client.helpdesk_client.doctype.support_ticket import support_ticket

	note = (note or "").strip()[:1000]
	kept = []
	if fixed:
		support_ticket.confirm_resolution(doc.ticket, note)
		text = _("Thank you for confirming. TBO Support closes the ticket.")
	else:
		support_ticket.reopen(doc.ticket, note)
		kept.append(_as_dict(_add(doc, {"direction": "Customer", "kind": "Text", "text": note})))
		text = _("Thank you. The ticket is open again, and a person from our team is on it.")
	kept.append(_as_dict(_add(doc, {"direction": "System", "kind": "Text", "text": text})))
	doc.db_set("last_message_at", now_datetime(), update_modified=False)
	return {"conversation": doc.name, "status": doc.status, "ticket": doc.ticket, "messages": kept}


def _own_files(files) -> list[dict]:
	"""Files the user uploaded here themselves, private: the hub fetches them like a ticket's."""
	files = frappe.parse_json(files) if isinstance(files, str) else files or []
	own = []
	for item in files[:10]:
		url = str((item or {}).get("file_url") or "")
		row = frappe.db.get_value(
			"File", {"file_url": url}, ["name", "file_name", "owner", "is_private"], as_dict=True
		)
		if row and row.owner == frappe.session.user and row.is_private:
			own.append({"file_url": url, "file_name": row.file_name, "file": row.name})
	return own


def _ticket_for(doc, reply: dict):
	"""TBO Support raised the ticket: this site keeps its own Support Ticket for it, with the chat's files."""
	fields = reply.get("fields") or {}
	labels = (
		("actual", _("What happened")),
		("expected", _("What I expected")),
		("steps", _("Steps")),
		("records", _("Records")),
		("since", _("Since when")),
		("scope", _("One record or many")),
		("worked_before", _("Worked before")),
	)
	description = "".join(
		f"<p><b>{label}:</b> {frappe.utils.escape_html(fields[key])}</p>"
		for key, label in labels
		if fields.get(key)
	)
	context = ticket_context(_settings())
	ticket = frappe.get_doc(
		{
			"doctype": "Support Ticket",
			"subject": (fields.get("title") or _("Support request"))[:140],
			"description": description or _("Raised from the support chat."),
			# raised already: the hub's pull must not import it again
			"status": "Open",
			"ticket_id": reply["ticket"],
			"raised_by": frappe.session.user,
			**{
				k: context[k]
				for k in ("user_roles", "error_logs", "code_identity", "raised_by_email", "raised_by_name")
			},
		}
	)
	ticket.flags.from_chat = True
	ticket.insert(ignore_permissions=True)
	for item in frappe.get_all(
		MESSAGE, filters={"conversation": doc.name, "files": ["is", "set"]}, pluck="files"
	):
		for f in frappe.parse_json(item) or []:
			frappe.db.set_value(
				"File",
				f.get("file"),
				{"attached_to_doctype": "Support Ticket", "attached_to_name": ticket.name},
				update_modified=False,
			)
	doc.db_set("ticket", ticket.name, update_modified=False)
	try:
		_relay(
			{
				"conversation": doc.hub_conversation,
				"client_conversation": doc.name,
				"user": _user(),
				"action": "linked",
				"client_ticket": ticket.name,
			}
		)
	except ChatUnavailable:
		frappe.log_error(title=f"Support chat: TBO Support did not hear of {ticket.name}")
