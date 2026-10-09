# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Read-only tools that tell the hub what runs on this site and what changed.

Copilot uses them to find a root cause: the code deployed (app, branch,
commit), the site's own customizations, the state after a deploy, and who
changed a record (a person, the system, an import or the hub).
"""

import json
import os
import re
import subprocess

import frappe
from frappe.utils import add_to_date, now_datetime

from helpdesk_client.mcp.tools import register_tool
from helpdesk_client.support_user import get_support_user

GIT_TIMEOUT_SECONDS = 5
CREDENTIALS_IN_URL = re.compile(r"(?<=://)[^/@\s]+@")
FRAME = re.compile(r'File "[^"]*?/apps/([^/"]+)/[^"]*", line \d+, in [^\n]+')

CUSTOMIZATIONS = {
	"Custom Field": ("dt", ["dt", "fieldname", "fieldtype", "label", "insert_after"]),
	"Property Setter": ("doc_type", ["doc_type", "field_name", "property", "value"]),
	"Client Script": ("dt", ["dt", "view", "enabled"]),
	"Server Script": ("reference_doctype", ["reference_doctype", "script_type", "doctype_event", "disabled"]),
	"Workflow": ("document_type", ["document_type", "workflow_name", "is_active"]),
	"Print Format": ("doc_type", ["doc_type", "standard", "disabled"]),
	"Notification": ("document_type", ["document_type", "event", "channel", "enabled"]),
}


# --- error helpers, shared with get_error_log ---


def app_of(error: str | None) -> str | None:
	"""The app whose code raised the error: the last frame under apps/<app>/."""
	frames = FRAME.findall(error or "")
	return frames[-1] if frames else None


def top_frames(error: str | None, count: int = 3) -> list[str]:
	"""The innermost frames of a traceback, closest to the failure last."""
	frames = [m.group(0) for m in FRAME.finditer(error or "")]
	return [f.split("/apps/", 1)[-1] for f in frames[-count:]]


def signature(error: str | None, method: str | None) -> str:
	lines = [line.strip() for line in (error or "").strip().splitlines() if line.strip()]
	last = lines[-1][:200] if lines else ""
	return f"{app_of(error) or '?'} | {method or '?'} | {last}"


# --- code identity ---


def strip_credentials(url: str | None) -> str | None:
	return CREDENTIALS_IN_URL.sub("", url) if url else url


def _git_dir(repo: str) -> str | None:
	git = os.path.join(repo, ".git")
	if os.path.isdir(git):
		return git
	if os.path.isfile(git):	 # a worktree: "gitdir: <path>"
		with open(git) as f:  # path is this bench's own app checkout - nosemgrep
			pointer = f.read().strip()
		if pointer.startswith("gitdir:"):
			return os.path.normpath(os.path.join(repo, pointer[7:].strip()))
	return None


def _read(path: str) -> str:
	try:
		with open(path) as f:  # files inside the app's own .git - nosemgrep
			return f.read()
	except OSError:
		return ""


def _resolve_ref(git_dir: str, ref: str) -> str | None:
	common = os.path.normpath(os.path.join(git_dir, _read(os.path.join(git_dir, "commondir")).strip() or "."))
	for base in dict.fromkeys((git_dir, common)):
		value = _read(os.path.join(base, ref)).strip()
		if value:
			return value
		for line in _read(os.path.join(base, "packed-refs")).splitlines():
			if line.endswith(" " + ref):
				return line.split(" ", 1)[0]
	return None


def _remotes(git_dir: str) -> dict:
	common = os.path.normpath(os.path.join(git_dir, _read(os.path.join(git_dir, "commondir")).strip() or "."))
	remotes, current = {}, None
	for line in _read(os.path.join(common, "config")).splitlines():
		line = line.strip()
		match = re.match(r'\[remote "([^"]+)"\]', line)
		if match:
			current = match.group(1)
		elif line.startswith("["):
			current = None
		elif current and line.startswith("url"):
			remotes[current] = strip_credentials(line.split("=", 1)[1].strip())
	return remotes


def _dirty(repo: str) -> bool | None:
	"""Uncommitted changes to tracked files; None when git is missing or too slow."""
	try:
		out = subprocess.run(  # fixed arguments, the app's own checkout - nosemgrep
			["git", "status", "--porcelain", "--untracked-files=no"],
			cwd=repo,
			capture_output=True,
			text=True,
			timeout=GIT_TIMEOUT_SECONDS,
			check=False,
		)
	except (OSError, subprocess.SubprocessError):
		return None
	return bool(out.stdout.strip()) if out.returncode == 0 else None


def _from_apps_json(app: str) -> dict:
	"""What bench recorded about the app (Press benches carry no .git in some images)."""
	try:
		apps = json.loads(_read(frappe.get_site_path("..", "apps.json")) or "{}")
	except ValueError:
		return {}
	resolution = (apps.get(app) or {}).get("resolution") or {}
	return {"commit": resolution.get("commit_hash"), "branch": resolution.get("branch"), "source": "apps.json"}


def code_identity(app: str) -> dict:
	repo = os.path.realpath(frappe.get_app_path(app, ".."))
	info = {"app": app}
	try:
		info["version"] = frappe.get_attr(f"{app}.__version__")
	except Exception:
		info["version"] = None
	git_dir = _git_dir(repo)
	if not git_dir:
		info.update(_from_apps_json(app))
		return info
	head = _read(os.path.join(git_dir, "HEAD")).strip()
	if head.startswith("ref:"):
		ref = head[4:].strip()
		info["branch"] = ref.removeprefix("refs/heads/")
		info["commit"] = _resolve_ref(git_dir, ref)
	else:
		info["branch"] = None  # detached HEAD
		info["commit"] = head or None
	info["remotes"] = _remotes(git_dir)
	info["dirty"] = _dirty(repo)
	info["source"] = "git"
	return info


def get_code_identity(apps=None, **_kwargs) -> str:
	"""Per installed app: version, branch, commit, remotes (no credentials) and uncommitted changes."""
	installed = frappe.get_installed_apps()
	wanted = [app for app in (apps or installed) if app in installed]
	return frappe.as_json([code_identity(app) for app in wanted], indent=2)


# --- customizations ---


def get_customizations(doctypes=None, since=None, limit: int = 100, **_kwargs) -> str:
	"""The site's own changes on top of the apps: custom fields, property setters, scripts, workflows, print formats, notifications."""
	limit = max(1, min(int(limit), 500))
	result = {}
	for doctype, (link_field, fields) in CUSTOMIZATIONS.items():
		filters = {}
		if doctypes:
			filters[link_field] = ["in", list(doctypes)]
		if since:
			filters["modified"] = [">=", since]
		try:
			rows = frappe.get_list(
				doctype,
				filters=filters,
				fields=["name", "modified", "modified_by", *fields],
				order_by="modified desc",
				limit_page_length=limit,
			)
		except frappe.PermissionError:
			rows = None	 # the support user may not read this kind; say so instead of failing
		result[doctype] = rows
	return frappe.as_json(result, indent=2)


# --- deploy status ---


def get_deploy_status(since=None, **_kwargs) -> str:
	"""After a deploy: patches run, the scheduler, the workers, and the errors since (top signatures)."""
	from frappe.utils.scheduler import is_scheduler_inactive

	since = since or add_to_date(now_datetime(), hours=-24)
	patches = frappe.get_all(
		"Patch Log",
		filters={"creation": [">=", since]},
		fields=["patch", "creation"],
		order_by="creation desc",
		limit_page_length=50,
	)
	errors = frappe.get_list(
		"Error Log",
		filters={"creation": [">=", since]},
		fields=["method", "error"],
		order_by="creation desc",
		limit_page_length=500,
	)
	counts = {}
	for row in errors:
		key = signature(row.error, row.method)
		counts[key] = counts.get(key, 0) + 1
	try:
		from frappe.utils.background_jobs import get_workers

		workers = len(get_workers())
	except Exception:
		workers = None
	return frappe.as_json(
		{
			"since": str(since),
			"scheduler_enabled": not is_scheduler_inactive(),
			"maintenance_mode": bool(frappe.conf.get("maintenance_mode")),
			"workers": workers,
			"patches": patches,
			"errors": {
				"count": len(errors),
				"top": [
					{"signature": key, "count": count}
					for key, count in sorted(counts.items(), key=lambda item: -item[1])[:10]
				],
			},
		},
		indent=2,
	)


# --- version history ---


def actor_of(owner: str, data_import=None) -> str:
	if data_import:
		return "import"
	if owner == get_support_user():
		return "hub"
	if owner in ("Administrator", "Guest"):
		return "system"
	return "person"


def get_version_history(doctype, name, since=None, limit: int = 20, **_kwargs) -> str:
	"""Who changed a record and what: each change with its actor (hub, system, import or person)."""
	frappe.has_permission(doctype, "read", name, throw=True)
	filters = {"ref_doctype": doctype, "docname": name}
	if since:
		filters["creation"] = [">=", since]
	fields = ["name", "owner", "creation", "data"]
	if frappe.get_meta("Version").has_field("data_import"):
		fields.append("data_import")
	versions = frappe.get_all(
		"Version",
		filters=filters,
		fields=fields,
		order_by="creation desc",
		limit_page_length=max(1, min(int(limit), 100)),
	)
	history = []
	for version in versions:
		try:
			data = json.loads(version.data or "{}")
		except ValueError:
			data = {}
		history.append(
			{
				"at": str(version.creation),
				"by": version.owner,
				"actor": actor_of(version.owner, version.get("data_import")),
				"changed": [
					{"field": change[0], "from": str(change[1])[:200], "to": str(change[2])[:200]}
					for change in (data.get("changed") or [])
					if isinstance(change, list | tuple) and len(change) == 3
				],
				"rows_added": len(data.get("added") or []),
				"rows_removed": len(data.get("removed") or []),
				"rows_changed": len(data.get("row_changed") or []),
			}
		)
	return frappe.as_json({"doctype": doctype, "name": name, "history": history}, indent=2)


# --- Register tools ---

register_tool(
	"get_code_identity",
	description="Which code runs on this site: per app the version, branch, commit, remotes and uncommitted changes.",
	input_schema={
		"type": "object",
		"properties": {
			"apps": {"type": "array", "items": {"type": "string"}, "description": "Only these apps. Default: all installed apps"},
		},
	},
	handler=get_code_identity,
	doctype_args=(),
	write=False,
)

register_tool(
	"get_customizations",
	description="The site's own customizations: custom fields, property setters, client and server scripts, workflows, print formats, notifications.",
	input_schema={
		"type": "object",
		"properties": {
			"doctypes": {"type": "array", "items": {"type": "string"}, "description": "Only customizations of these doctypes"},
			"since": {"type": "string", "description": "Only customizations changed at or after this datetime"},
			"limit": {"type": "integer", "description": "Max rows per kind (default 100, at most 500)"},
		},
	},
	handler=get_customizations,
	doctype_args=("doctypes",),
	write=False,
)

register_tool(
	"get_deploy_status",
	description="The site after a deploy: patches run, scheduler, workers, and errors since a time with their top signatures.",
	input_schema={
		"type": "object",
		"properties": {
			"since": {"type": "string", "description": "Look at changes at or after this datetime. Default: the last 24 hours"},
		},
	},
	handler=get_deploy_status,
	doctype_args=(),
	write=False,
)

register_tool(
	"get_version_history",
	description="Who changed a record and what, newest first: each change with its actor (hub, system, import or person).",
	input_schema={
		"type": "object",
		"properties": {
			"doctype": {"type": "string", "description": "The DocType name"},
			"name": {"type": "string", "description": "The document name"},
			"since": {"type": "string", "description": "Only changes at or after this datetime"},
			"limit": {"type": "integer", "description": "Max changes (default 20, at most 100)"},
		},
		"required": ["doctype", "name"],
	},
	handler=get_version_history,
	write=False,
)
