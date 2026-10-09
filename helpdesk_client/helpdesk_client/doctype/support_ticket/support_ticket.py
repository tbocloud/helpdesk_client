# Copyright (c) 2026, Wahni IT Solutions Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from helpdesk_client.support_user import get_support_user
from helpdesk_client.utils.notifications import notify_stage_change, notify_status_change

RESOLVED_STATUSES = ("Resolved", "Closed")


class SupportTicket(Document):
	def on_update(self):
		"""Notify the reporter when the status or the stage changes.

		The Hub writes status and stage here, so this is the only place a
		change can be observed — the client never polls the Helpdesk.
		"""
		previous = self.get_doc_before_save()
		if not previous:
			return
		self.notify_status_change(previous)
		self.notify_stage_change(previous)

	def notify_status_change(self, previous):
		if previous.status == self.status:
			return
		self.db_set("last_synced", now_datetime(), update_modified=False)
		notify_status_change(self, self.status)

	def notify_stage_change(self, previous):
		if (previous.stage, previous.stage_message) == (self.stage, self.stage_message):
			return
		notify_stage_change(self)


def is_raiser(doc, user: str | None = None) -> bool:
	"""The person who made the ticket, or the one it was raised for."""
	user = user or frappe.session.user
	return user in (doc.owner, doc.raised_by)


def get_permission_query_conditions(user):
	user = user or frappe.session.user
	if "System Manager" in frappe.get_roles(user):
		return ""
	escaped = frappe.db.escape(user)
	return f"(`tabSupport Ticket`.`owner` = {escaped} or `tabSupport Ticket`.`raised_by` = {escaped})"


def has_permission(doc, ptype=None, user=None):
	"""A single ticket is for its owner, the person it was raised for, and System Managers."""
	user = user or frappe.session.user
	if user == "Administrator" or "System Manager" in frappe.get_roles(user):
		return True
	return is_raiser(doc, user)


def _require_raiser(doc):
	if not is_raiser(doc) and "System Manager" not in frappe.get_roles():
		frappe.throw(_("Only the person who raised the ticket can do this."), frappe.PermissionError)


def _is_resolved(doc) -> bool:
	return doc.stage == "Resolved" or doc.status in RESOLVED_STATUSES


@frappe.whitelist(methods=["POST"])
def request_close(ticket: str) -> str:
	"""The raiser asks to close: flag it; the Hub closes the HD Ticket next cycle."""
	doc = frappe.get_doc("Support Ticket", ticket)
	_require_raiser(doc)
	doc.db_set("close_requested", 1)
	return "ok"


@frappe.whitelist(methods=["POST"])
def confirm_resolution(ticket: str, note: str = "") -> dict:
	"""The raiser says it is fixed: recorded here, and the Hub closes the ticket on its next cycle."""
	doc = frappe.get_doc("Support Ticket", ticket)
	_require_raiser(doc)
	if not _is_resolved(doc):
		frappe.throw(_("There is nothing to confirm yet: the ticket is not resolved."))
	doc.update(
		{
			"customer_confirmation": "Confirmed",
			"confirmation_note": (note or "").strip()[:1000],
			"confirmed_at": now_datetime(),
			"reopen_requested": 0,
			"close_requested": 1,
		}
	)
	doc.save(ignore_permissions=True)
	return {"ok": True, "confirmation": "Confirmed"}


@frappe.whitelist(methods=["POST"])
def reopen(ticket: str, note: str) -> dict:
	"""The raiser says it is still broken: a person at TBO takes the ticket over."""
	doc = frappe.get_doc("Support Ticket", ticket)
	_require_raiser(doc)
	if not (note or "").strip():
		frappe.throw(_("Please say what is still wrong."))
	if not _is_resolved(doc):
		frappe.throw(_("The ticket is still open; add a comment instead."))
	doc.update(
		{
			"customer_confirmation": "Reopened",
			"confirmation_note": note.strip()[:1000],
			"confirmed_at": now_datetime(),
			"reopen_requested": 1,
			"reopen_count": (doc.reopen_count or 0) + 1,
			"close_requested": 0,
		}
	)
	doc.save(ignore_permissions=True)
	return {"ok": True, "confirmation": "Reopened", "reopen_count": doc.reopen_count}


def notify_reply(doc, method):
	"""Comment after_insert: a support-user comment on a Support Ticket is an
	agent reply pushed by the Hub — notify the reporter with the text."""
	if doc.reference_doctype != "Support Ticket" or doc.comment_type != "Comment":
		return
	if doc.owner != get_support_user():
		return
	raised_by = frappe.db.get_value("Support Ticket", doc.reference_name, "raised_by")
	if not raised_by or raised_by == doc.owner:
		return
	frappe.get_doc(
		{
			"doctype": "Notification Log",
			"for_user": raised_by,
			"type": "Alert",
			"subject": _("Support replied on {0}").format(doc.reference_name),
			"email_content": doc.content,
			"document_type": "Support Ticket",
			"document_name": doc.reference_name,
		}
	).insert(ignore_permissions=True)
