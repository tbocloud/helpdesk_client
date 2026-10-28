# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""What TBO Support (the hub) writes on this site's own tickets, and reads back.

The hub calls these as the support user over token auth (the request gate in
hub_gate.py allows this module). They touch only this app's Support Ticket
and its comments, so the ticket conversation works whether or not the site
allows MCP write operations.
"""

import json

import frappe
from frappe import _
from frappe.utils import get_datetime, now_datetime, strip_html

from helpdesk_client import __version__
from helpdesk_client.api import _require_support_user
from helpdesk_client.support_user import get_support_user

CAPABILITIES = ["hub_api_v1", "write_guard_v1", "chat_v1"]
CHAT_DIRECTIONS = ("Assistant", "Agent", "System")
# the labels this app's status field accepts
CLIENT_STATUSES = ("Pending", "Open", "Replied", "Paused", "Resolved", "Closed")
# hub labels that mean "waiting on something", shown here as Paused
PAUSED_LABELS = ("Waiting on Task", "Waiting on Customer", "On Hold")
STAGES = ("Received", "Working on it", "Fix scheduled", "Resolved", "With our team", "Waiting for you")
UPDATE_KINDS = ("Stage", "Reply", "System")
WRITABLE_FIELDS = (
	"ticket_id",
	"status",
	"status_label",
	"priority",
	"category",
	"stage",
	"stage_message",
	"handled_by",
	"resolution",
	"deployed_commit",
	"deployed_at",
)
MAX_CHANGES = 500


def capabilities_info() -> dict:
	return {"client_version": __version__, "capabilities": list(CAPABILITIES)}


@frappe.whitelist(methods=["POST"])
def capabilities() -> dict:
	"""What this client can do, so the hub picks the right path."""
	_require_support_user()
	return capabilities_info()


def map_hub_status(label: str | None) -> str | None:
	"""The status this app can show for a hub label; None when there is no sensible one."""
	if not label:
		return None
	if label in CLIENT_STATUSES:
		return label
	if label in PAUSED_LABELS:
		return "Paused"
	return None


@frappe.whitelist(methods=["POST"])
def update_ticket(name: str, values: dict | str) -> dict:
	"""The hub's view of a ticket: number, status, priority, stage, resolution.

	Fields outside the allow-list are ignored, not refused, so an older
	client never fails a newer hub. A status this app cannot show keeps the
	old status and lands in `status_label`.
	"""
	_require_support_user()
	values = _parse(values, "values")
	doc = frappe.get_doc("Support Ticket", name)
	applied, ignored = [], []
	for field, value in values.items():
		if field not in WRITABLE_FIELDS:
			ignored.append(field)
			continue
		if field == "status":
			if _set(doc, "status_label", value):
				applied.append("status_label")
			value = map_hub_status(value)
			if value is None:
				ignored.append("status")
				continue
		if field == "stage" and value and value not in STAGES:
			ignored.append("stage")
			continue
		if _set(doc, field, value):
			applied.append(field)
	applied = list(dict.fromkeys(applied))
	if applied:
		doc.flags.from_hub = True
		doc.save(ignore_permissions=True)
	return {"ok": True, "applied": applied, "ignored": ignored}


@frappe.whitelist(methods=["POST"])
def post_message(
	conversation: str,
	hub_ref: str,
	text: str = "",
	direction: str = "Assistant",
	kind: str = "Text",
	card: str | dict | None = None,
) -> dict:
	"""A message from TBO Support to one of this site's chats (progress, the team's reply), shown live.

	The same `hub_ref` is never added twice, so the hub may retry freely.
	"""
	from helpdesk_client import chat

	_require_support_user()
	hub_ref = _ref(hub_ref)
	if direction not in CHAT_DIRECTIONS:
		frappe.throw(_("Unknown direction: {0}").format(direction))
	doc = frappe.get_doc(chat.CONVERSATION, conversation)
	row = chat._add(doc, {"direction": direction, "kind": kind, "text": text, "card": card}, hub_ref)
	if not row:
		return {"ok": True, "duplicate": True}
	doc.db_set("last_message_at", now_datetime(), update_modified=False)
	frappe.publish_realtime(
		"helpdesk_client_chat",
		{"conversation": doc.name, "message": chat._as_dict(row)},
		user=doc.user,
		after_commit=True,
	)
	return {"ok": True, "duplicate": False}


@frappe.whitelist(methods=["POST"])
def add_update(
	name: str,
	hub_ref: str,
	stage: str = "",
	message: str = "",
	author_name: str = "TBO Support",
	kind: str = "Stage",
) -> dict:
	"""One entry on the ticket's updates; a Stage entry also moves the ticket to that stage.

	The same `hub_ref` is never added twice, so the hub may retry freely.
	"""
	_require_support_user()
	hub_ref = _ref(hub_ref)
	if kind not in UPDATE_KINDS:
		frappe.throw(_("Unknown update kind: {0}").format(kind))
	if kind == "Stage" and stage not in STAGES:
		frappe.throw(_("Unknown stage: {0}").format(stage))
	doc = frappe.get_doc("Support Ticket", name)
	if _has_ref(doc, hub_ref):
		return {"ok": True, "duplicate": True}
	doc.append("updates", _row(hub_ref, kind, stage, message, author_name))
	if kind == "Stage":
		doc.stage = stage
		doc.stage_message = (message or "")[:2000]
	doc.flags.from_hub = True
	doc.save(ignore_permissions=True)
	return {"ok": True, "duplicate": False}


@frappe.whitelist(methods=["POST"])
def post_reply(name: str, hub_ref: str, content: str, author_name: str = "TBO Support") -> dict:
	"""An agent's reply: a comment on the ticket (the raiser is notified) and a Reply entry; never posted twice."""
	_require_support_user()
	hub_ref = _ref(hub_ref)
	if not strip_html(content or "").strip():
		frappe.throw(_("The reply is empty"))
	doc = frappe.get_doc("Support Ticket", name)
	if _has_ref(doc, hub_ref):
		return {"ok": True, "duplicate": True}
	comment = frappe.get_doc(
		{
			"doctype": "Comment",
			"comment_type": "Comment",
			"reference_doctype": "Support Ticket",
			"reference_name": doc.name,
			"content": content,
			"comment_email": get_support_user(),
			"comment_by": (author_name or "TBO Support")[:140],
		}
	).insert(ignore_permissions=True)
	row = _row(hub_ref, "Reply", "", strip_html(content), author_name)
	row["comment"] = comment.name
	doc.append("updates", row)
	doc.flags.from_hub = True
	doc.save(ignore_permissions=True)
	return {"ok": True, "duplicate": False, "comment": comment.name}


@frappe.whitelist(methods=["POST"])
def get_ticket_changes(since: str, limit: int = 200) -> dict:
	"""Tickets changed here since `since` (confirmations, reopens, close requests), oldest first,
	and `server_time` to pass as the next `since`."""
	_require_support_user()
	since_dt = get_datetime(since) if since else None
	if not since_dt:
		frappe.throw(_("since must be a datetime"))
	server_time = now_datetime()
	tickets = frappe.get_all(
		"Support Ticket",
		filters={"modified": [">", since_dt]},
		fields=[
			"name",
			"ticket_id",
			"status",
			"stage",
			"close_requested",
			"customer_confirmation",
			"confirmation_note",
			"confirmed_at",
			"reopen_requested",
			"reopen_count",
			"modified",
		],
		order_by="modified asc",
		limit=max(1, min(int(limit or MAX_CHANGES), MAX_CHANGES)),
	)
	return {"server_time": str(server_time), "tickets": tickets}


def _parse(value, what: str) -> dict:
	if isinstance(value, str):
		try:
			value = json.loads(value)
		except ValueError:
			frappe.throw(_("{0} must be JSON").format(what))
	if not isinstance(value, dict):
		frappe.throw(_("{0} must be an object").format(what))
	return value


def _set(doc, field: str, value) -> bool:
	value = None if value == "" else value
	if (doc.get(field) or None) == value:
		return False
	doc.set(field, value)
	return True


def _ref(hub_ref: str) -> str:
	hub_ref = (hub_ref or "").strip()
	if not hub_ref:
		frappe.throw(_("hub_ref is required"))
	return hub_ref[:140]


def _has_ref(doc, hub_ref: str) -> bool:
	return any(row.hub_ref == hub_ref for row in doc.updates)


def _row(hub_ref: str, kind: str, stage: str, message: str, author_name: str) -> dict:
	return {
		"hub_ref": hub_ref,
		"kind": kind,
		"stage": (stage or "")[:140],
		"message": (message or "")[:2000],
		"author_name": (author_name or "TBO Support")[:140],
		"posted_at": now_datetime(),
	}
