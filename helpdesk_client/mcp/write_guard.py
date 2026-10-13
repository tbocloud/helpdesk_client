# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Every write TBO Support (the hub) makes on this site passes here first.

In order: support enabled; the write switch; the doctype not blocked (and in the
allowed list, when there is one); a child row checked as its parent; nothing on
the never list; the doctype on this site's write list with that action; and on
Production an approval the hub signed for exactly that record. The hub's support
user is still a System Manager here, so this site decides, whatever the hub asks.

Each write, applied or refused, is recorded in HDS Change Log.
"""

import base64
import hashlib
import hmac
import json
import time

import frappe
from frappe import _
from frappe.utils import get_datetime

ENVIRONMENTS = ("Production", "UAT", "Sandbox")

# never written by the hub, whatever the write list says
NEVER_WRITE = frozenset(
	{
		"User",
		"Role",
		"Has Role",
		"DocPerm",
		"Custom DocPerm",
		"User Permission",
		"Role Profile",
		"Module Profile",
		"System Settings",
		"Email Account",
		"Email Domain",
		"OAuth Client",
		"Social Login Key",
		"Connected App",
		"Token Cache",
		"Server Script",
		"Client Script",
		"Scheduled Job Type",
		"Custom Field",
		"Property Setter",
		"DocType",
		"Workflow",
		"Print Format",
		"Bulk Update",
		"Data Import",
		"HDS Support Settings",
		"HDS Change Log",
	}
)

# an action and the write list's checkbox that allows it; there is none for delete
FLAGS = {
	"update": "may_update",
	"create": "may_create",
	"submit": "may_submit_cancel",
	"cancel": "may_submit_cancel",
}


class ChangedSince(frappe.ValidationError):
	"""The record no longer holds the values the approval was given for."""


# --- the site --------------------------------------------------------------------


def environment() -> str:
	value = frappe.db.get_single_value("HDS Support Settings", "site_environment", cache=False)
	return value if value in ENVIRONMENTS else "Production"


def approval_key() -> str:
	from frappe.utils.password import get_decrypted_password

	return (
		get_decrypted_password(
			"HDS Support Settings", "HDS Support Settings", "approval_key", raise_exception=False
		)
		or ""
	)


# --- the signed approval -----------------------------------------------------------


def _b64(raw: bytes) -> str:
	return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(text: str) -> bytes:
	return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def sign_approval(payload: dict, key: str) -> str:
	"""`<payload>.<signature>`: base64url JSON, then its HMAC-SHA256 under the approval key (the hub signs the same way)."""
	body = _b64(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
	signature = hmac.new(key.encode(), body.encode(), hashlib.sha256).digest()
	return f"{body}.{_b64(signature)}"


def read_approval(token: str | None) -> dict:
	"""The approval's content, once its signature and time are checked; refused otherwise."""
	if not token:
		frappe.throw(
			_("On a Production site every write from TBO Support needs its signed approval."),
			frappe.PermissionError,
		)
	key = approval_key()
	if not key:
		frappe.throw(
			_("This site has no approval key; connect it to TBO Support again."), frappe.PermissionError
		)
	body, _sep, signature = str(token).partition(".")
	expected = hmac.new(key.encode(), body.encode(), hashlib.sha256).digest()
	try:
		valid = bool(signature) and hmac.compare_digest(_unb64(signature), expected)
		payload = json.loads(_unb64(body)) if valid else None
	except (ValueError, TypeError):
		valid, payload = False, None
	if not valid or not isinstance(payload, dict) or payload.get("v") != 1:
		frappe.throw(_("The approval's signature is not valid."), frappe.PermissionError)
	if float(payload.get("exp") or 0) < time.time():
		frappe.throw(_("The approval has expired."), frappe.PermissionError)
	return payload


def change_digest(change: dict, expect=None) -> str:
	"""What exactly a change does: its new values and rows, and the old values it expects.

	The hub signs this digest with each record, so an approval covers these values
	and no others: sha256 of the sorted, compact JSON of
	`{values, rows, add_rows, expect}` (the change as parse_change gives it).
	"""
	if isinstance(expect, str):
		expect = frappe.parse_json(expect)
	content = {
		"values": change.get("values") or {},
		"rows": change.get("rows") or [],
		"add_rows": change.get("add_rows") or [],
		"expect": expect if expect is not None else None,
	}
	return hashlib.sha256(
		json.dumps(content, sort_keys=True, separators=(",", ":"), default=str).encode()
	).hexdigest()


def names(payload: dict, doctype: str, name: str, action: str, item: str = "", digest: str = "") -> bool:
	"""Whether the approval covers this record and action: the same change item and
	the same values when the approval says which."""
	for record in payload.get("records") or []:
		if not isinstance(record, dict):
			continue
		if (record.get("doctype"), record.get("name") or "", record.get("action")) != (
			doctype,
			name or "",
			action,
		):
			continue
		if item and record.get("item") != item:
			continue
		if record.get("digest") and record.get("digest") != digest:
			continue
		return True
	return False


# --- what a call writes --------------------------------------------------------------


def parse_change(change) -> dict:
	"""One change to one record, as check_change and apply_change take it."""
	if isinstance(change, str):
		try:
			change = json.loads(change)
		except ValueError:
			change = None
	if not isinstance(change, dict):
		frappe.throw(_("A change must be an object."))
	action = change.get("action") or "update"
	if action not in ("update", "create"):
		frappe.throw(_("A change either updates a record or creates one, not {0}.").format(action))
	values = change.get("values") or {}
	rows = change.get("rows") or []
	add_rows = change.get("add_rows") or []
	if (
		not isinstance(values, dict)
		or not isinstance(rows, list)
		or not isinstance(add_rows, list)
		or not all(isinstance(row, dict) for row in rows + add_rows)
	):
		frappe.throw(_("A change's values must be an object, and its rows lists of objects."))
	if not change.get("doctype") or (action == "update" and not change.get("name")):
		frappe.throw(_("A change names its doctype, and the record it updates."))
	return {
		"item": str(change.get("item") or ""),
		"action": action,
		"doctype": str(change["doctype"]),
		"name": str(change.get("name") or "") if action == "update" else "",
		"values": values,
		"rows": rows,
		"add_rows": add_rows,
	}


def tool_action(tool: str, arguments: dict) -> str:
	if tool in ("set_value", "set_values"):
		return "update"
	if tool == "create_doc":
		return "create"
	if tool == "delete_doc":
		return "delete"
	if tool == "run_doc_method":
		return str(arguments.get("method") or "")
	if tool == "apply_change":
		return parse_change(arguments.get("change"))["action"]
	return ""


def describe(tool: str, arguments: dict) -> dict:
	"""The record a write tool call is about: for the change log, the checks and the approval."""
	entry = {"tool": tool, "action": "", "doctype": "", "name": "", "item": ""}
	try:
		if tool == "apply_change":
			change = parse_change(arguments.get("change"))
			entry.update(
				action=change["action"], doctype=change["doctype"], name=change["name"], item=change["item"]
			)
		else:
			entry.update(
				action=tool_action(tool, arguments),
				doctype=str(arguments.get("doctype") or ""),
				name=str(arguments.get("name") or ""),
			)
	except frappe.ValidationError:
		pass  # a malformed change is refused by check(), with its reason
	return entry


def _record_for(doctype: str, name: str) -> tuple[str, str]:
	"""A child-table row is written through its parent, so the parent is what the lists judge."""
	if doctype and name and frappe.db.exists("DocType", doctype) and frappe.get_meta(doctype).istable:
		row = frappe.db.get_value(doctype, name, ["parenttype", "parent"], as_dict=True)
		if row:
			return row.parenttype, row.parent
	return doctype, name


# --- the checks ------------------------------------------------------------------------


def check_never(doctype: str):
	if doctype in NEVER_WRITE:
		frappe.throw(_("TBO Support never changes {0} records.").format(doctype), frappe.PermissionError)


def check_lists(doctype: str, action: str):
	"""The never list and this site's write list."""
	check_never(doctype)
	flag = FLAGS.get(action)
	if not flag:
		frappe.throw(
			_("TBO Support may not {0} records on this site.").format(action or _("change")),
			frappe.PermissionError,
		)
	row = next(
		(
			row
			for row in frappe.get_single("HDS Support Settings").write_doctypes
			if row.doctype_name == doctype
		),
		None,
	)
	if not row:
		frappe.throw(
			_("{0} is not on this site's write list (HDS Support Settings).").format(doctype),
			frappe.PermissionError,
		)
	if not row.get(flag):
		frappe.throw(
			_("This site's write list does not let TBO Support {0} {1} records.").format(action, doctype),
			frappe.PermissionError,
		)


def check(tool: str, arguments: dict, need_approval: bool = True) -> dict | None:
	"""Every check a write from the hub must pass; the approval it carried, if any. Refusals raise PermissionError.

	`need_approval=False` runs the same checks without the signed approval (check_change asks it).
	"""
	from helpdesk_client.mcp.access_control import (
		check_child_table_write,
		check_doctype_access,
		check_enabled,
		check_write_enabled,
	)

	check_enabled()
	check_write_enabled()
	if tool == "apply_change":
		parse_change(arguments.get("change"))  # a malformed change is refused before anything else
	entry = describe(tool, arguments)
	if not entry["doctype"]:
		return None  # clear_cache: the write switch is enough
	check_doctype_access(entry["doctype"], is_write=True)
	if tool != "apply_change":
		check_child_table_write(tool, entry["doctype"], arguments)
	parent, _parent_name = _record_for(entry["doctype"], entry["name"])
	if parent != entry["doctype"]:
		# a table row changes its parent record: the row's own doctype must not be
		# on the never list, and the parent must be open to updates
		check_never(entry["doctype"])
		check_lists(parent, "update")
	else:
		check_lists(entry["doctype"], entry["action"])
	token = arguments.get("approval")
	if not need_approval or (environment() != "Production" and not token):
		return None
	payload = read_approval(token)
	digest = (
		change_digest(parse_change(arguments.get("change")), arguments.get("expect"))
		if tool == "apply_change"
		else ""
	)
	if not names(payload, entry["doctype"], entry["name"], entry["action"], entry["item"], digest):
		frappe.throw(
			_("The approval does not cover {0} {1} ({2}).").format(
				entry["doctype"], entry["name"] or _("a new record"), entry["action"]
			),
			frappe.PermissionError,
		)
	return payload


# --- the change log ---------------------------------------------------------------------


def _json(value) -> str | None:
	if value in (None, {}, []):
		return None
	return frappe.as_json(value)[:20000]


def record(
	entry: dict,
	status: str,
	approval: dict | None = None,
	old=None,
	new=None,
	error: str = "",
	started: float | None = None,
	name: str = "",
):
	"""One HDS Change Log row for a write from the hub, applied or not."""
	approval = approval or {}
	try:
		approved_at = get_datetime(approval.get("approved_at")) if approval.get("approved_at") else None
	except Exception:
		approved_at = None
	log = frappe.get_doc(
		{
			"doctype": "HDS Change Log",
			"status": status,
			"tool": entry.get("tool"),
			"action": entry.get("action"),
			"reference_doctype": entry.get("doctype") or None,
			"reference_name": name or entry.get("name") or None,
			"ticket": str(approval.get("ticket") or "")[:140],
			"change_set": str(approval.get("change_set") or "")[:140],
			"change_item": entry.get("item") or "",
			"approved_by": str(approval.get("approved_by") or "")[:140],
			"approved_at": approved_at,
			"environment": environment(),
			"old_values": _json(old),
			"new_values": _json(new),
			"error": str(error or "")[:1000],
			"duration_ms": round((time.monotonic() - started) * 1000) if started else None,
		}
	)
	log.flags.ignore_links = True
	log.insert(ignore_permissions=True)
	return log


def already_applied(change_set: str, item: str) -> bool:
	"""A change item that was applied once is not applied again (a retried call would create twice)."""
	return bool(
		change_set
		and item
		and frappe.db.exists(
			"HDS Change Log", {"change_set": change_set, "change_item": item, "status": "Applied"}
		)
	)


def snapshot(tool: str, arguments: dict) -> dict | None:
	"""The values set_value and set_values are about to replace, for the change log."""
	if tool == "set_value":
		fields = [arguments.get("fieldname")]
	elif tool == "set_values":
		values = arguments.get("values")
		if isinstance(values, str):
			try:
				values = json.loads(values)
			except ValueError:
				return None
		fields = list(values or {}) if isinstance(values, dict) else []
	else:
		return None
	try:
		doc = frappe.get_doc(arguments.get("doctype"), arguments.get("name"))
	except Exception:
		return None
	return {field: doc.get(field) for field in fields if field}
