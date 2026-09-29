# Copyright (c) 2026, Wahni IT Solutions Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime

from helpdesk_client.support_user import get_support_user
from helpdesk_client.utils.notifications import notify_status_change


class SupportTicket(Document):
	def on_update(self):
		"""Notify the reporter when the status changes.

		Under the zero-client-key flow the Hub writes status here over MCP,
		so this is the only place a status change can be observed — the
		client no longer polls the Helpdesk.
		"""
		previous = self.get_doc_before_save()
		if not previous or previous.status == self.status:
			return

		self.db_set("last_synced", now_datetime(), update_modified=False)
		notify_status_change(self, self.status)


def get_permission_query_conditions(user):
	user = user or frappe.session.user
	if "System Manager" in frappe.get_roles(user):
		return ""
	return f"(`tabSupport Ticket`.`owner` = {frappe.db.escape(user)})"


@frappe.whitelist()
def request_close(ticket: str):
	"""Owner asks to close: flag it; the Hub closes the HD Ticket next cycle."""
	doc = frappe.get_doc("Support Ticket", ticket)
	if doc.owner != frappe.session.user and "System Manager" not in frappe.get_roles():
		frappe.throw(frappe._("Only the ticket owner can close it."), frappe.PermissionError)
	doc.db_set("close_requested", 1)
	return "ok"


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
			"subject": frappe._("Support replied on {0}").format(doc.reference_name),
			"email_content": doc.content,
			"document_type": "Support Ticket",
			"document_name": doc.reference_name,
		}
	).insert(ignore_permissions=True)
