# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Access control for MCP tool calls based on HDS Support Settings."""

import frappe
from frappe import _


def check_enabled():
	"""Every MCP tool needs support to be enabled, with or without a doctype."""
	if not frappe.db.get_single_value("HDS Support Settings", "enabled"):
		frappe.throw(_("Helpdesk Support Client is disabled"), frappe.PermissionError)


def check_write_enabled():
	"""Every write tool needs the master write switch, with or without a doctype."""
	if not frappe.db.get_single_value("HDS Support Settings", "allow_write_operations"):
		frappe.throw(_("Write operations are disabled"), frappe.PermissionError)


def check_doctype_access(doctype, is_write=False):
	"""Check if the given doctype is accessible via MCP.

	Raises frappe.PermissionError if access is denied.
	"""
	settings = frappe.get_single("HDS Support Settings")

	if not settings.enabled:
		frappe.throw(_("Helpdesk Support Client is disabled"), frappe.PermissionError)

	# Check write permission
	if is_write and not settings.allow_write_operations:
		frappe.throw(_("Write operations are disabled"), frappe.PermissionError)

	# Check blocked doctypes
	blocked = {row.doctype_name for row in settings.blocked_doctypes}
	if doctype in blocked:
		frappe.throw(_("Access to {0} is blocked").format(doctype), frappe.PermissionError)

	# Check allowed doctypes (whitelist mode)
	allowed = {row.doctype_name for row in settings.allowed_doctypes}
	if allowed and doctype not in allowed:
		frappe.throw(_("{0} is not in the allowed doctypes list").format(doctype), frappe.PermissionError)


def check_child_table_write(tool: str, doctype: str, arguments: dict):
	"""A write to a child-table row saves its parent, so the parent is what must be allowed.

	Creating or deleting child rows on their own is refused: they are written
	through the parent document, which then goes through the normal checks.
	"""
	if not frappe.get_meta(doctype).istable:
		return
	if tool in ("create_doc", "delete_doc"):
		frappe.throw(
			_("{0} is a child table; write its rows through the parent document").format(doctype),
			frappe.PermissionError,
		)
	row = frappe.db.get_value(doctype, arguments.get("name"), ["parenttype", "parent"], as_dict=True)
	if not row:
		frappe.throw(_("{0} {1} not found").format(doctype, arguments.get("name")), frappe.DoesNotExistError)
	check_doctype_access(row.parenttype, is_write=True)
