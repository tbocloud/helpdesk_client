# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""What a new ticket carries about where the user was and who they are."""

import json

import frappe
from frappe.utils import add_to_date, now_datetime

from helpdesk_client.utils import get_cache

CODE_IDENTITY_CACHE_KEY = "helpdesk_client:code_identity"
CODE_IDENTITY_CACHE_SECONDS = 600


def ticket_context(settings, page_route: str = "", ref_doctype: str = "", ref_docname: str = "") -> dict:
	"""The page, the record, the user's roles and recent errors, the site's apps; the raiser's contact."""
	user = frappe.session.user
	email, full_name = raiser_identity(user, settings.fallback_contact_email)
	return {
		"page_route": (page_route or "")[:140],
		"ref_doctype": (ref_doctype or "")[:140],
		"ref_docname": (ref_docname or "")[:140],
		"user_roles": json.dumps(sorted(set(frappe.get_roles(user)) - {"All", "Guest"})),
		"error_logs": json.dumps(recent_error_logs(user)),
		"code_identity": json.dumps(code_identity()),
		"raised_by_email": email,
		"raised_by_name": full_name,
	}


def raiser_identity(user: str, fallback_email: str | None = None) -> tuple[str, str]:
	"""The user's email and name; Administrator's placeholder address gives way to the site's fallback contact."""
	info = frappe.db.get_value("User", user, ["email", "full_name"], as_dict=True) or frappe._dict()
	if user == "Administrator" and fallback_email:
		email = fallback_email
	else:
		email = info.email if "@" in (info.email or "") else (user if "@" in user else (fallback_email or ""))
	return email, info.full_name or user


def recent_error_logs(user: str, hours: int = 24, limit: int = 10) -> list[dict]:
	"""The user's own Error Log rows of the last `hours`, newest first, trimmed."""
	rows = frappe.get_all(
		"Error Log",
		filters={"owner": user, "creation": [">=", add_to_date(now_datetime(), hours=-hours)]},
		fields=["name", "method", "error", "reference_doctype", "reference_name", "creation"],
		order_by="creation desc",
		limit=limit,
	)
	return [
		{
			"name": row.name,
			"method": row.method,
			"error": (row.error or "")[:500],
			"reference": f"{row.reference_doctype}/{row.reference_name}" if row.reference_doctype else "",
			"at": str(row.creation),
		}
		for row in rows
	]


def code_identity() -> list[dict]:
	"""The installed apps and their versions (cached for ten minutes); the git commit comes later."""
	cache = get_cache()
	cached = cache.get_value(CODE_IDENTITY_CACHE_KEY)
	if cached:
		return cached
	apps = []
	for app in frappe.get_installed_apps():
		try:
			version = frappe.get_attr(f"{app}.__version__")
		except Exception:
			version = None
		apps.append({"app": app, "version": version})
	cache.set_value(CODE_IDENTITY_CACHE_KEY, apps, expires_in_sec=CODE_IDENTITY_CACHE_SECONDS)
	return apps
