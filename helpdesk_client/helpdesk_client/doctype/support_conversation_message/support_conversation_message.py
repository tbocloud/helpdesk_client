# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class SupportConversationMessage(Document):
	"""One message of a chat with TBO Support."""

	pass


def get_permission_query_conditions(user):
	user = user or frappe.session.user
	if "System Manager" in frappe.get_roles(user):
		return ""
	escaped = frappe.db.escape(user)
	return (
		"`tabSupport Conversation Message`.`conversation` in "
		f"(select name from `tabSupport Conversation` where `user` = {escaped})"
	)


def has_permission(doc, ptype=None, user=None):
	user = user or frappe.session.user
	if user == "Administrator" or "System Manager" in frappe.get_roles(user):
		return True
	return frappe.db.get_value("Support Conversation", doc.conversation, "user") == user
