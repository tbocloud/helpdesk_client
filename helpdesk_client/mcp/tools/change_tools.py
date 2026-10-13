# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Corrections TBO Support prepared and a person approved, one record at a time.

A change is `{item, action: update|create, doctype, name, values: {field: value},
rows: [{table, name, values}], add_rows: [{table, values}]}`: `rows` are existing
table rows, `add_rows` new ones. `check_change` writes nothing and runs none of
the site's own code; `apply_change` saves with the site's normal validation, and
refuses a record whose changed fields no longer hold the values the approval was
given for.
"""

import frappe
from frappe import _
from frappe.model import no_value_fields, table_fields
from frappe.utils import cstr, escape_html, get_datetime, getdate

from helpdesk_client.mcp import write_guard
from helpdesk_client.mcp.tools import register_tool


def _value_problem(df, value) -> str:
	"""Why `value` does not fit the field, or ""."""
	if value in (None, ""):
		return _("is required") if df.reqd else ""
	try:
		if df.fieldtype in ("Int", "Check"):
			int(value)
		elif df.fieldtype in ("Float", "Currency", "Percent"):
			float(value)
		elif df.fieldtype == "Date":
			getdate(value)
		elif df.fieldtype == "Datetime":
			get_datetime(value)
	except frappe.ValidationError:
		frappe.clear_last_message()  # getdate throws for a person to read; here it is a finding
		return _("cannot hold {0}").format(cstr(value)[:60])
	except (ValueError, TypeError):
		return _("cannot hold {0}").format(cstr(value)[:60])
	if isinstance(value, dict | list):
		return _("cannot hold a list or an object")
	if df.fieldtype == "Select":
		options = [option for option in (df.options or "").split("\n")]
		if cstr(value) not in options:
			return _("must be one of {0}").format(", ".join(o for o in options if o))
	if df.fieldtype == "Link" and df.options and not frappe.db.exists(df.options, value):
		return _("names no {0} called {1}").format(df.options, cstr(value)[:60])
	if df.fieldtype == "Data" and len(cstr(value)) > (df.length or 140):
		return _("is longer than {0} characters").format(df.length or 140)
	return ""


def _field_problems(meta, values: dict, where: str, submitted: bool = False) -> list[str]:
	problems = []
	for field, value in values.items():
		df = meta.get_field(field)
		if not df:
			problems.append(_("{0} has no field {1}").format(where, field))
		elif df.fieldtype in table_fields:
			problems.append(_("{0}: the table {1} is changed row by row").format(where, field))
		elif df.fieldtype in no_value_fields:
			problems.append(_("{0}: {1} holds no value").format(where, field))
		elif df.read_only or df.fieldtype == "Read Only":
			problems.append(_("{0}: {1} is read-only").format(where, field))
		elif submitted and not df.allow_on_submit:
			problems.append(
				_(
					"{0} is submitted and {1} cannot change after submit: a person corrects it (cancel and amend, or a return)"
				).format(where, field)
			)
		elif problem := _value_problem(df, value):
			problems.append(f"{where}: {field} {problem}")
	return problems


def _table(meta, table: str):
	df = meta.get_field(table) if table else None
	return df if df and df.fieldtype in table_fields else None


def _row(doc, row: dict):
	return next(
		(found for found in doc.get(row.get("table")) or [] if found.name == row.get("name")),
		None,
	)


def _current(doc, change: dict) -> dict:
	"""The values the change replaces: the record's fields, and the table rows it changes."""
	rows = {}
	for row in change["rows"]:
		found = _row(doc, row)
		if found:
			rows[found.name] = {field: found.get(field) for field in row.get("values") or {}}
	return {"values": {field: doc.get(field) for field in change["values"]}, "rows": rows}


def _plain(value):
	"""A value as it travels in JSON, so a read and an approval compare equal."""
	if value is None:
		return ""
	if isinstance(value, bool):
		return int(value)
	if isinstance(value, int | float):
		return round(float(value), 9)
	return cstr(value)


def _same(current: dict, expect: dict) -> bool:
	for field, value in (expect.get("values") or {}).items():
		if _plain((current.get("values") or {}).get(field)) != _plain(value):
			return False
	for name, values in (expect.get("rows") or {}).items():
		row = (current.get("rows") or {}).get(name)
		if row is None or any(_plain(row.get(f)) != _plain(v) for f, v in (values or {}).items()):
			return False
	return True


def _change_problems(meta, change: dict, doc) -> list[str]:
	"""What is wrong with the change itself: its fields, values, table rows, and what a new record lacks."""
	submitted = bool(doc and doc.docstatus == 1)
	problems = [_("{0} {1} is cancelled").format(doc.doctype, doc.name)] if doc and doc.docstatus == 2 else []
	problems += _field_problems(meta, change["values"], change["doctype"], submitted)
	for row in change["rows"]:
		df = _table(meta, row.get("table"))
		if not df:
			problems.append(_("{0} has no table {1}").format(change["doctype"], row.get("table")))
		elif doc and not _row(doc, row):
			problems.append(_("{0} has no row {1} in {2}").format(doc.name, row.get("name"), df.fieldname))
		else:
			problems += _field_problems(
				frappe.get_meta(df.options), row.get("values") or {}, df.options, submitted
			)
	for row in change["add_rows"]:
		df = _table(meta, row.get("table"))
		if not df:
			problems.append(_("{0} has no table {1}").format(change["doctype"], row.get("table")))
		elif submitted:
			problems.append(_("{0} is submitted: its tables cannot grow").format(doc.name))
		else:
			problems += _field_problems(frappe.get_meta(df.options), row.get("values") or {}, df.options)
	if change["action"] == "create":
		missing = [
			df.fieldname
			for df in meta.fields
			if df.reqd
			and not df.default
			and df.fieldtype not in no_value_fields
			and df.fieldtype not in table_fields
			and change["values"].get(df.fieldname) in (None, "")
		]
		if missing:
			problems.append(_("A new {0} needs {1}").format(change["doctype"], ", ".join(missing)))
	return problems


def check_change(change, **_kwargs):
	"""Checks one change without saving it: would this site allow it, do the fields and values fit, and what does the record hold now."""
	from helpdesk_client.mcp.access_control import check_doctype_access

	change = write_guard.parse_change(change)
	check_doctype_access(change["doctype"])  # reading the record obeys the read lists
	problems = []
	try:
		write_guard.check("apply_change", {"change": change}, need_approval=False)
	except (frappe.PermissionError, frappe.ValidationError) as e:
		problems.append(cstr(e))
	meta = frappe.get_meta(change["doctype"])
	doc, current = None, {}
	if change["action"] == "update":
		if meta.issingle and change["name"] != change["doctype"]:
			frappe.throw(_("{0} is a single settings record named {0}.").format(change["doctype"]))
		if not meta.issingle and not frappe.db.exists(change["doctype"], change["name"]):
			frappe.throw(
				_("{0} {1} not found").format(change["doctype"], change["name"]), frappe.DoesNotExistError
			)
		doc = frappe.get_doc(change["doctype"], change["name"])
		current = _current(doc, change)
	problems += _change_problems(meta, change, doc)
	return frappe.as_json(
		{
			"ok": not problems,
			"problems": problems,
			"current": current,
			"docstatus": doc.docstatus if doc else 0,
			"environment": write_guard.environment(),
		}
	)


def apply_change(change, expect=None, approval=None, **_kwargs):
	"""Applies one approved change to one record, if it still holds the values the approval was given for."""
	change = write_guard.parse_change(change)
	payload = write_guard.read_approval(approval) if approval else {}
	meta = frappe.get_meta(change["doctype"])
	if change["action"] == "create":
		if write_guard.already_applied(payload.get("change_set"), change["item"]):
			raise write_guard.ChangedSince(_("This change was applied already."))
		if problems := _change_problems(meta, change, None):
			frappe.throw("; ".join(problems))
		doc = frappe.get_doc({"doctype": change["doctype"], **change["values"]})
		for row in change["add_rows"]:
			doc.append(row["table"], row.get("values") or {})
		doc.insert()
		old, new = {}, {"values": change["values"], "add_rows": change["add_rows"]}
	else:
		if expect is None:
			frappe.throw(_("An update needs the values the approval was given for (expect)."))
		doc = frappe.get_doc(change["doctype"], change["name"])
		before = _current(doc, change)
		if not _same(before, frappe.parse_json(expect) or {}):
			raise write_guard.ChangedSince(
				_("{0} {1} changed since it was checked; it was left as it is.").format(doc.doctype, doc.name)
			)
		if problems := _change_problems(meta, change, doc):
			frappe.throw("; ".join(problems))
		doc.update(change["values"])
		for row in change["rows"]:
			found = _row(doc, row)
			if not found:
				frappe.throw(_("{0} has no row {1}").format(doc.name, row.get("name")))
			found.update(row.get("values") or {})
		for row in change["add_rows"]:
			doc.append(row["table"], row.get("values") or {})
		doc.save()
		old, new = before, _current(doc, change)
		if change["add_rows"]:
			new["add_rows"] = change["add_rows"]
	_note(doc, payload, old, new, created=change["action"] == "create")
	return frappe.as_json(
		{"status": "applied", "doctype": doc.doctype, "name": doc.name, "old": old, "new": new}
	)


def _note(doc, payload: dict, old: dict, new: dict, created: bool = False):
	"""A line on the record's timeline: who asked, who approved, what changed."""
	heading = (_("Created by TBO Support") if created else _("Changed by TBO Support")) + (
		" "
		+ _("for ticket {0}, approved by {1} (change set {2})").format(
			payload.get("ticket"), payload.get("approved_by"), payload.get("change_set")
		)
		if payload
		else ""
	)
	parts = [
		f"{field}: {cstr((old.get('values') or {}).get(field))} → {cstr(value)}"
		for field, value in (new.get("values") or {}).items()
	]
	for name, values in (new.get("rows") or {}).items():
		parts += [
			f"{name}.{field}: {cstr(((old.get('rows') or {}).get(name) or {}).get(field))} → {cstr(value)}"
			for field, value in values.items()
		]
	if new.get("add_rows"):
		parts.append(_("{0} new rows").format(len(new["add_rows"])))
	doc.add_comment("Info", escape_html((heading + (": " + "; ".join(parts) if parts else ""))[:2000]))


CHANGE_SCHEMA = {
	"type": "object",
	"description": "One change to one record.",
	"properties": {
		"item": {"type": "string", "description": "TBO Support's id for this change"},
		"action": {"type": "string", "enum": ["update", "create"]},
		"doctype": {"type": "string"},
		"name": {"type": "string", "description": "The record to update; not for create"},
		"values": {"type": "object", "description": "Field: new value"},
		"rows": {
			"type": "array",
			"items": {"type": "object"},
			"description": "Existing table rows to change: {table, name, values}",
		},
		"add_rows": {
			"type": "array",
			"items": {"type": "object"},
			"description": "New table rows: {table, values}",
		},
	},
	"required": ["doctype"],
}

register_tool(
	"check_change",
	description="Check one change to one record without saving it: whether this site would allow it, whether the fields and values fit, and the record's current values. Writes nothing and runs none of the site's own code.",
	input_schema={"type": "object", "properties": {"change": CHANGE_SCHEMA}, "required": ["change"]},
	handler=check_change,
	doctype_args=(),
	write=False,
)

register_tool(
	"apply_change",
	description="Apply one approved change to one record. `expect` holds the values the approval was given for: a record that no longer holds them is left as it is. On a Production site `approval` is TBO Support's signed approval for this record.",
	input_schema={
		"type": "object",
		"properties": {
			"change": CHANGE_SCHEMA,
			"expect": {
				"type": "object",
				"description": "{values: {field: old value}, rows: {row: {field: old value}}}",
			},
			"approval": {"type": "string"},
		},
		"required": ["change"],
	},
	handler=apply_change,
	doctype_args=(),
)
