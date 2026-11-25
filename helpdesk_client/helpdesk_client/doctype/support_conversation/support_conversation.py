# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class SupportConversation(Document):
	"""A chat with TBO Support's assistant from the Support button; the ticket it raised."""

	pass


def get_permission_query_conditions(user):
	user = user or frappe.session.user
	if "System Manager" in frappe.get_roles(user):
		return ""
	return f"`tabSupport Conversation`.`user` = {frappe.db.escape(user)}"


def has_permission(doc, ptype=None, user=None):
	"""A chat is its user's own, and System Managers'."""
	user = user or frappe.session.user
	if user == "Administrator" or "System Manager" in frappe.get_roles(user):
		return True
	return doc.user == user
