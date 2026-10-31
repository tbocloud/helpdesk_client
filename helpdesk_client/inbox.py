# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""The user's support inbox (TBO Copilot Phase 13): their tickets, each with its chat, and their other chats.

A ticket's dot says whose move it is: green once they confirmed the fix (or closed it themselves), red while
TBO Support waits for them (a fix to check, a question to answer), orange while the team works on it. A ticket
closes only when the user confirms; until then a fix waiting for their check is brought up every 3 days.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, formatdate, get_datetime, now_datetime

from helpdesk_client.utils.context import refuse_hub_user

TICKET, CONVERSATION, MESSAGE = "Support Ticket", "Support Conversation", "Support Conversation Message"
GREEN, RED, ORANGE = "green", "red", "orange"
# hub labels that mean the team is waiting for the customer (Waiting on Task is the team's own wait)
WAITING_LABELS = ("Replied", "Waiting on Customer")
OPEN_CHAT_STATES = ("Talking", "Summary", "Before a person")
REMIND_EVERY_DAYS = 3
SUMMARY_CHARS = 80
TICKET_FIELDS = [
	"name",
	"ticket_id",
	"subject",
	"status",
	"status_label",
	"stage",
	"stage_message",
	"handled_by",
	"customer_confirmation",
	"confirmed_at",
	"close_requested",
	"last_synced",
	"modified",
]


def require_user():
	if frappe.session.user == "Guest":
		frappe.throw(_("Please sign in to see your support tickets."), frappe.PermissionError)
	refuse_hub_user()


def summary(text: str | None) -> str:
	"""The ticket's problem in one short line."""
	line = " ".join(str(text or "").split())
	return line if len(line) <= SUMMARY_CHARS else line[: SUMMARY_CHARS - 1].rstrip() + "…"


def _answered_since_last_change(t) -> bool:
	"""The user's confirm or reopen came after TBO Support last moved the ticket's status."""
	if not t.confirmed_at:
		return False
	return not t.last_synced or get_datetime(t.confirmed_at) >= get_datetime(t.last_synced)


def state(ticket) -> dict:
	"""The ticket's dot, what it means, and what the user must do (only when red)."""
	t = _plain(ticket)
	fresh = _answered_since_last_change(t)
	if fresh and t.customer_confirmation == "Reopened":
		return _state(ORANGE, _("You reopened it: a person from TBO Support is on it"))
	if fresh and t.customer_confirmation == "Confirmed":
		return _state(
			GREEN, _("Fixed: you confirmed it on {0}").format(formatdate(t.confirmed_at)), closed=True
		)
	if t.status == "Closed":
		return _state(GREEN, _("Closed"), closed=True)
	if t.close_requested:
		return _state(GREEN, _("Closing: you asked to close it"), closed=True)
	if t.status == "Resolved" or t.stage == "Resolved":
		return _state(
			RED,
			_("Fixed: please check it and confirm it works"),
			_("Check the fix and confirm it works"),
			confirm=True,
		)
	if t.stage == "Waiting for you" or t.status == "Replied" or t.status_label in WAITING_LABELS:
		asked = (t.stage_message if t.stage == "Waiting for you" else "") or _last_team_word(t.name)
		return _state(
			RED,
			_("TBO Support is waiting for your answer"),
			_("Answer the team: {0}").format(summary(asked)) if asked else _("Answer the team's question"),
		)
	if t.status == "Pending":
		return _state(ORANGE, _("Sent to TBO Support"))
	return _state(ORANGE, _(t.stage) if t.stage else _("TBO Support is working on it"))


def _plain(ticket) -> frappe._dict:
	return frappe._dict(ticket.as_dict() if isinstance(ticket, Document) else ticket)


def _state(dot: str, line: str, action: str = "", confirm: bool = False, closed: bool = False) -> dict:
	return {"dot": dot, "line": line, "action": action, "confirm": confirm, "closed": closed}


def _last_team_word(ticket: str) -> str:
	rows = frappe.get_all(
		"Support Ticket Update",
		filters={"parent": ticket, "parenttype": TICKET, "kind": "Reply"},
		fields=["message"],
		order_by="posted_at desc",
		limit=1,
	)
	return rows[0].message if rows else ""


def _my_tickets(fields=None, limit: int = 200) -> list:
	user = frappe.session.user
	return frappe.get_all(
		TICKET,
		or_filters={"owner": user, "raised_by": user},
		fields=fields or TICKET_FIELDS,
		order_by="modified desc",
		limit=limit,
	)


def my_ticket(name: str):
	"""One of the user's own tickets (the one who raised it, or the one it was raised for)."""
	from helpdesk_client.helpdesk_client.doctype.support_ticket.support_ticket import is_raiser

	doc = frappe.get_doc(TICKET, name)
	if not is_raiser(doc):
		frappe.throw(_("This is not your ticket."), frappe.PermissionError)
	return doc


def ticket_card(ticket) -> dict:
	"""What the chat shows about its ticket: its name, summary and dot."""
	t = _plain(ticket)
	return {
		"name": t.name,
		"ticket_id": t.ticket_id,
		"summary": summary(t.subject),
		**state(t),
	}


@frappe.whitelist()
def overview() -> dict:
	"""The user's tickets (open ones first), the red ones again as actions, and their other chats."""
	require_user()
	tickets = _my_tickets()
	chats = frappe.get_all(
		CONVERSATION,
		filters={"user": frappe.session.user},
		fields=["name", "ticket", "status", "last_message_at", "creation"],
		order_by="creation desc",
		limit=300,
	)
	by_ticket = {c.ticket: c for c in chats if c.ticket}
	rows = []
	for t in tickets:
		chat = by_ticket.get(t.name)
		activity = max(get_datetime(t.modified), get_datetime((chat and chat.last_message_at) or t.modified))
		rows.append({**ticket_card(t), "conversation": chat and chat.name, "last_activity": str(activity)})
	rows.sort(key=lambda r: r["last_activity"], reverse=True)
	rows.sort(key=lambda r: r["closed"])  # open ones first, each group newest first
	return {
		"tickets": rows,
		"actions": [r for r in rows if r["dot"] == RED],
		"chats": _chats([c for c in chats if not c.ticket]),
	}


def _chats(chats: list) -> list[dict]:
	"""The chats that did not become tickets, by their first line; an untouched one only while open."""
	first = {}
	if chats:
		for m in frappe.get_all(
			MESSAGE,
			filters={
				"conversation": ["in", [c.name for c in chats]],
				"direction": "Customer",
				"text": ["is", "set"],
			},
			fields=["conversation", "text"],
			order_by="creation asc",
		):
			first.setdefault(m.conversation, m.text)
	rows = []
	for c in chats:
		is_open = c.status in OPEN_CHAT_STATES
		if c.name not in first and not is_open:
			continue
		rows.append(
			{
				"name": c.name,
				"summary": summary(first.get(c.name)) or _("New chat"),
				"open": is_open,
				"last_activity": str(c.last_message_at or c.creation),
			}
		)
	rows.sort(key=lambda r: r["last_activity"], reverse=True)
	return rows


def actions_count(user: str | None = None) -> int:
	"""How many of the user's tickets wait for them (the red button's number)."""
	user = user or frappe.session.user
	if user == "Guest":
		return 0
	tickets = frappe.get_all(
		TICKET,
		or_filters={"owner": user, "raised_by": user},
		filters={"status": ["!=", "Closed"]},
		fields=TICKET_FIELDS,
		limit=200,
	)
	return sum(1 for t in tickets if state(t)["dot"] == RED)


@frappe.whitelist()
def ticket_status(ticket: str) -> dict:
	"""What's the status? Answered here at once, from the ticket TBO Support keeps up to date."""
	require_user()
	t = my_ticket(ticket)
	now = state(t)
	lines = [now["line"]]
	if t.stage_message and t.stage_message not in lines:
		lines.append(t.stage_message)
	latest = sorted(t.updates or [], key=lambda u: str(u.posted_at or ""))[-1:]
	facts = [
		(_("Ticket"), t.name + (f" (#{t.ticket_id})" if t.ticket_id else "")),
		(_("Stage"), _(t.stage or t.status)),
		(_("With"), t.handled_by),
	]
	if latest:
		u = latest[0]
		facts.append(
			(
				_("Last update"),
				"{} · {}: {}".format(
					formatdate(u.posted_at), u.author_name or _("TBO Support"), summary(u.message or u.stage)
				),
			)
		)
	if now["action"]:
		facts.append((_("Needed from you"), now["action"]))
	return {
		"direction": "System",
		"kind": "Status",
		"text": now["line"],
		"card": {"title": _("Where your ticket stands"), "lines": lines, "facts": [f for f in facts if f[1]]},
	}


def refresh_for(ticket) -> None:
	"""The panel, the full page and the red button reload when a ticket changes."""
	for user in {ticket.owner, ticket.raised_by} - {None, "", "Guest", "Administrator"}:
		frappe.publish_realtime(
			"helpdesk_client_inbox", {"ticket": ticket.name}, user=user, after_commit=True
		)


def chat_route(ticket: str) -> str:
	return f"/app/support-chat/{ticket}"


def remind_unconfirmed() -> int:
	"""Daily: a fix waiting for the user's check is brought up again every 3 days, until they answer."""
	cutoff = add_days(now_datetime(), -REMIND_EVERY_DAYS)
	reminded = 0
	for t in frappe.get_all(
		TICKET,
		filters={"status": ["!=", "Closed"]},
		fields=[*TICKET_FIELDS, "raised_by", "owner", "confirmation_reminded_at"],
	):
		if not state(t)["confirm"]:
			continue
		since = t.confirmation_reminded_at or t.last_synced or t.modified
		if get_datetime(since) > cutoff:
			continue
		user = t.raised_by or t.owner
		if user and frappe.db.exists("User", {"name": user, "enabled": 1}):
			frappe.get_doc(
				{
					"doctype": "Notification Log",
					"for_user": user,
					"type": "Alert",
					"subject": _("Please check the fix on {0} and confirm it works: {1}").format(
						t.name, summary(t.subject)
					),
					"document_type": TICKET,
					"document_name": t.name,
					"link": chat_route(t.name),
				}
			).insert(ignore_permissions=True)
			reminded += 1
		frappe.db.set_value(TICKET, t.name, "confirmation_reminded_at", now_datetime(), update_modified=False)
	return reminded
