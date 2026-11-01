# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def _readers(doc, followers_only: bool = False) -> list[str]:
	"""Who hears about a status or stage change: the reporter, and the colleagues who follow the ticket."""
	users = ([] if followers_only else [doc.raised_by]) + [f.user for f in doc.get("followers") or []]
	return [u for u in dict.fromkeys(users) if u and u not in ("Guest", "Administrator")]


def notify_status_change(doc, new_status, followers_only: bool = False):
	"""Raise a desk notification for the user who reported the ticket.

	Called from Support Ticket.on_update, so it fires whether the status
	was changed by the Hub over MCP or by a local edit.
	"""
	reference = doc.ticket_id or doc.name
	for user in _readers(doc, followers_only):
		frappe.get_doc(
			{
				"doctype": "Notification Log",
				"for_user": user,
				"type": "Alert",
				"subject": _("Your support ticket #{0} is now {1}").format(reference, _(new_status)),
				"document_type": "Support Ticket",
				"document_name": doc.name,
			}
		).insert(ignore_permissions=True)


def notify_stage_change(doc):
	"""Raise a desk notification for the reporter when TBO Support moves the ticket to a new stage."""
	if not doc.stage:
		return

	reference = doc.ticket_id or doc.name
	for user in _readers(doc):
		frappe.get_doc(
			{
				"doctype": "Notification Log",
				"for_user": user,
				"type": "Alert",
				"subject": _("Your support ticket #{0}: {1}").format(reference, _(doc.stage)),
				"email_content": doc.stage_message or "",
				"document_type": "Support Ticket",
				"document_name": doc.name,
			}
		).insert(ignore_permissions=True)


def notify_action_needed(doc, action: str):
	"""The ticket waits for the reporter (Phase 13): the notice says what to do and opens its chat."""
	if not doc.raised_by:
		return

	from helpdesk_client.inbox import chat_route

	frappe.get_doc(
		{
			"doctype": "Notification Log",
			"for_user": doc.raised_by,
			"type": "Alert",
			"subject": _("{0} needs you: {1}").format(doc.name, action),
			"email_content": doc.stage_message or "",
			"document_type": "Support Ticket",
			"document_name": doc.name,
			"link": chat_route(doc.name),
		}
	).insert(ignore_permissions=True)
