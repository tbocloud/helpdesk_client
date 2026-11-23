# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

import json
import time

import frappe

TOOL_REGISTRY: dict[str, dict] = {}

WRITE_TOOLS = {
	"set_value",
	"set_values",
	"create_doc",
	"delete_doc",
	"run_doc_method",
	"clear_cache",
	"apply_change",
}
WRITE_SAVEPOINT = "hds_hub_write"


def register_tool(name, *, description, input_schema, handler, doctype_args=("doctype",), write=None):
	"""Register an MCP tool in the global registry.

	`doctype_args` names every argument that holds a doctype (a name or a list
	of names); each one is checked against the allowed and blocked lists.
	"""
	TOOL_REGISTRY[name] = {
		"name": name,
		"description": description,
		"inputSchema": input_schema,
		"handler": handler,
		"doctype_args": tuple(doctype_args),
		"write": name in WRITE_TOOLS if write is None else bool(write),
	}


def get_tool_definitions() -> list[dict]:
	"""Return tool definitions for tools/list response."""
	return [
		{
			"name": t["name"],
			"description": t["description"],
			"inputSchema": t["inputSchema"],
		}
		for t in TOOL_REGISTRY.values()
	]


# Refusals the caller caused (no access, bad input, missing document). They are
# answered as tool errors but never written to Error Log: logging them let the
# AI read its own refusals back through get_error_log and buried real errors.
EXPECTED_ERRORS = (
	frappe.PermissionError,
	frappe.ValidationError,
	frappe.DoesNotExistError,
	frappe.AuthenticationError,
)


def execute_tool(name: str, arguments: dict) -> dict:
	"""Execute a tool and return MCP-formatted result."""
	from helpdesk_client.mcp.access_control import check_doctype_access, check_enabled

	if name not in TOOL_REGISTRY:
		return {
			"content": [{"type": "text", "text": f"Unknown tool: {name}"}],
			"isError": True,
		}

	tool = TOOL_REGISTRY[name]
	if tool["write"]:
		return _execute_write(name, tool, arguments)
	try:
		# The switch applies to every tool, whether or not it names a doctype
		check_enabled()
		for arg in tool["doctype_args"]:
			value = arguments.get(arg)
			for doctype in value if isinstance(value, list | tuple) else [value]:
				if doctype:
					check_doctype_access(doctype)

		result = tool["handler"](**arguments)
		return {
			"content": [{"type": "text", "text": result}],
			"isError": False,
		}
	except EXPECTED_ERRORS as e:
		return {
			"content": [{"type": "text", "text": f"Error executing {name}: {e}"}],
			"isError": True,
		}
	except Exception as e:
		frappe.log_error(f"MCP tool error: {name}", str(e))
		return {
			"content": [{"type": "text", "text": f"Error executing {name}: {e}"}],
			"isError": True,
		}


def _execute_write(name: str, tool: dict, arguments: dict) -> dict:
	"""A write from the hub: this site's guard first, then the tool; either way one line in HDS Change Log."""
	from helpdesk_client.mcp import write_guard

	started = time.monotonic()
	entry = write_guard.describe(name, arguments)
	approval = None
	frappe.db.savepoint(WRITE_SAVEPOINT)
	try:
		approval = write_guard.check(name, arguments)
	except Exception as e:
		return _write_failed(entry, approval, e, started, "Refused")
	before = write_guard.snapshot(name, arguments)
	try:
		result = tool["handler"](**arguments)
	except Exception as e:
		refused = isinstance(e, write_guard.ChangedSince | frappe.PermissionError)
		return _write_failed(entry, approval, e, started, "Refused" if refused else "Failed")
	old, new, record = _written(name, arguments, result, before)
	if entry["doctype"]:
		write_guard.record(entry, "Applied", approval, old=old, new=new, started=started, name=record)
	frappe.db.commit()  # the write and its line in the change log together - nosemgrep
	return {"content": [{"type": "text", "text": result}], "isError": False}


def _write_failed(entry: dict, approval, error: Exception, started: float, status: str) -> dict:
	try:
		frappe.db.rollback(save_point=WRITE_SAVEPOINT)
	except Exception:
		frappe.db.rollback()  # the tool committed past the savepoint
	if not isinstance(error, EXPECTED_ERRORS):
		frappe.log_error(f"MCP tool error: {entry['tool']}", str(error))
	if entry["doctype"]:
		from helpdesk_client.mcp import write_guard

		write_guard.record(entry, status, approval, error=str(error), started=started)
		frappe.db.commit()  # a refused write is recorded although nothing was written - nosemgrep
	return {
		"content": [{"type": "text", "text": f"Error executing {entry['tool']}: {error}"}],
		"isError": True,
	}


def _written(name: str, arguments: dict, result: str, before: dict | None) -> tuple:
	"""The old and new values of a write that went through, and the record's name, for the change log."""
	try:
		info = json.loads(result) if isinstance(result, str) else {}
	except ValueError:
		info = {}
	if name == "apply_change":
		return info.get("old"), info.get("new"), info.get("name") or ""
	if name == "set_value":
		return before, {arguments.get("fieldname"): arguments.get("value")}, ""
	values = arguments.get("values")
	if isinstance(values, str):
		values = frappe.parse_json(values)
	if name == "set_values":
		return before, values, ""
	if name == "create_doc":
		return None, values, info.get("name") or ""
	if name == "run_doc_method":
		return None, {"method": arguments.get("method"), "docstatus": info.get("docstatus")}, ""
	return None, None, ""
