# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

import frappe

TOOL_REGISTRY: dict[str, dict] = {}

WRITE_TOOLS = {"set_value", "set_values", "create_doc", "delete_doc", "run_doc_method", "clear_cache"}


def register_tool(name, *, description, input_schema, handler):
	"""Register an MCP tool in the global registry."""
	TOOL_REGISTRY[name] = {
		"name": name,
		"description": description,
		"inputSchema": input_schema,
		"handler": handler,
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
	from helpdesk_client.mcp.access_control import (
		check_child_table_write,
		check_doctype_access,
		check_enabled,
		check_write_enabled,
	)

	if name not in TOOL_REGISTRY:
		return {
			"content": [{"type": "text", "text": f"Unknown tool: {name}"}],
			"isError": True,
		}

	tool = TOOL_REGISTRY[name]
	try:
		# The switches apply to every tool, whether or not it names a doctype
		check_enabled()
		is_write = name in WRITE_TOOLS
		if is_write:
			check_write_enabled()
		doctype = arguments.get("doctype")
		if doctype:
			check_doctype_access(doctype, is_write=is_write)
			if is_write:
				check_child_table_write(name, doctype, arguments)

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
