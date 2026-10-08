# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""MCP tools for writing/modifying Frappe documents."""

import frappe

from helpdesk_client.mcp.tools import register_tool


def set_value(doctype, name, fieldname, value, **_kwargs):
	"""Set a single field value on a document."""
	frappe.set_value(doctype, name, fieldname, value)
	frappe.db.commit()  # each MCP write tool call is its own unit of work - nosemgrep
	return frappe.as_json(
		{
			"status": "success",
			"doctype": doctype,
			"name": name,
			"fieldname": fieldname,
			"value": value,
		}
	)


def set_values(doctype, name, values, **_kwargs):
	"""Set multiple field values on a document."""
	if isinstance(values, str):
		import json

		values = json.loads(values)
	doc = frappe.get_doc(doctype, name)
	doc.update(values)
	doc.save()
	frappe.db.commit()  # each MCP write tool call is its own unit of work - nosemgrep
	return frappe.as_json(
		{
			"status": "success",
			"doctype": doctype,
			"name": name,
			"updated_fields": list(values.keys()),
		}
	)


def create_doc(doctype, values, **_kwargs):
	"""Create a new document."""
	if isinstance(values, str):
		import json

		values = json.loads(values)
	values["doctype"] = doctype
	doc = frappe.get_doc(values)
	doc.insert()
	frappe.db.commit()  # each MCP write tool call is its own unit of work - nosemgrep
	return frappe.as_json(
		{
			"status": "created",
			"doctype": doctype,
			"name": doc.name,
		}
	)


def delete_doc(doctype, name, **_kwargs):
	"""Delete a document."""
	frappe.delete_doc(doctype, name)
	frappe.db.commit()  # each MCP write tool call is its own unit of work - nosemgrep
	return frappe.as_json(
		{
			"status": "deleted",
			"doctype": doctype,
			"name": name,
		}
	)


# The only controller methods run_doc_method may call: the two lifecycle
# transitions, each checked against the matching permission. Whitelisted
# methods are not accepted any more: Document.rename and merge are
# whitelisted on every doctype, and Bulk Update's method rewrites any
# doctype with raw SQL, so "whitelisted" is not a safe boundary here.
ALLOWED_DOC_METHODS = {"submit", "cancel"}


def run_doc_method(doctype, name, method, args=None, **_kwargs):
	"""Submit or cancel a document, with the calling user's permissions."""
	if method not in ALLOWED_DOC_METHODS:
		frappe.throw(
			f"Method '{method}' is not permitted via MCP; only submit and cancel are",
			frappe.PermissionError,
		)

	doc = frappe.get_doc(doctype, name)
	doc.check_permission(method)
	if method == "submit":
		doc.submit()
	else:
		doc.cancel()
	frappe.db.commit()  # each MCP write tool call is its own unit of work - nosemgrep
	return frappe.as_json(
		{
			"status": "success",
			"doctype": doctype,
			"name": name,
			"method": method,
			"docstatus": doc.docstatus,
		}
	)


def clear_cache(**_kwargs):
	"""Clear the site cache. Gated by the write switch like every write tool."""
	frappe.clear_cache()
	return frappe.as_json({"status": "cache_cleared"})


# --- Register tools ---

register_tool(
	"set_value",
	description="Set a single field value on a document. Runs validation and permission checks. Example: set_value('Task', 'TASK-0001', 'priority', 'High'). Do not write 'status' on submittable documents directly - use run_doc_method with 'submit'/'cancel'.",
	input_schema={
		"type": "object",
		"properties": {
			"doctype": {"type": "string", "description": "The DocType name"},
			"name": {"type": "string", "description": "The document name/ID"},
			"fieldname": {"type": "string", "description": "The field to update"},
			"value": {"description": "The new value to set"},
		},
		"required": ["doctype", "name", "fieldname", "value"],
	},
	handler=set_value,
)

register_tool(
	"set_values",
	description="Set multiple field values on a document at once.",
	input_schema={
		"type": "object",
		"properties": {
			"doctype": {"type": "string", "description": "The DocType name"},
			"name": {"type": "string", "description": "The document name/ID"},
			"values": {"type": "object", "description": "Key-value pairs of fields to update"},
		},
		"required": ["doctype", "name", "values"],
	},
	handler=set_values,
)

register_tool(
	"create_doc",
	description="Create a new document in the specified DocType.",
	input_schema={
		"type": "object",
		"properties": {
			"doctype": {"type": "string", "description": "The DocType name"},
			"values": {"type": "object", "description": "Field values for the new document"},
		},
		"required": ["doctype", "values"],
	},
	handler=create_doc,
)

register_tool(
	"delete_doc",
	description="Delete a document. Use with caution.",
	input_schema={
		"type": "object",
		"properties": {
			"doctype": {"type": "string", "description": "The DocType name"},
			"name": {"type": "string", "description": "The document name/ID to delete"},
		},
		"required": ["doctype", "name"],
	},
	handler=delete_doc,
)

register_tool(
	"run_doc_method",
	description="Submit or cancel a document. Only 'submit' and 'cancel' are permitted.",
	input_schema={
		"type": "object",
		"properties": {
			"doctype": {"type": "string", "description": "The DocType name"},
			"name": {"type": "string", "description": "The document name/ID"},
			"method": {"type": "string", "enum": ["submit", "cancel"], "description": "'submit' or 'cancel'"},
		},
		"required": ["doctype", "name", "method"],
	},
	handler=run_doc_method,
)

register_tool(
	"clear_cache",
	description="Clear the site cache. Useful after making configuration changes.",
	input_schema={
		"type": "object",
		"properties": {},
	},
	handler=clear_cache,
)
