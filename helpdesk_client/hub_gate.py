# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""The support user's API key opens only the support doors.

The hub signs in with the support user's API key. That user keeps whatever
roles the customer gave it (System Manager on older installs), so without
this gate the same key would reach every standard REST endpoint on the site.
A key session (one with an Authorization header) may call only the endpoints
below. A person who logged in through the one-time link has a normal browser
session with no Authorization header: it is not limited to these endpoints,
but it holds only while TBO Support's access does (see end_revoked_session).
"""

import hashlib

import frappe
from frappe import _

from helpdesk_client.support_user import get_support_user

ALLOWED_PATH_PREFIXES = (
	"/api/method/helpdesk_client.mcp.handler.handle",
	"/api/method/helpdesk_client.hub_api.",
	"/api/method/helpdesk_client.api.register_connection",
	"/api/method/helpdesk_client.api.deregister",
	"/api/method/helpdesk_client.api.rotate_credentials",
	"/api/method/helpdesk_client.api.generate_login_url",
	"/api/method/frappe.auth.get_logged_user",
	# the hub downloads recordings and screenshots attached to tickets
	"/private/files/",
	"/files/",
)


def is_allowed_for_key_session(path: str) -> bool:
	"""Whether a request path is one the hub's key may call."""
	return bool(path) and path.startswith(ALLOWED_PATH_PREFIXES)


def gate(user: str, path: str, has_authorization_header: bool) -> None:
	"""Refuse a key session of the support user outside the support endpoints."""
	if not has_authorization_header or user != get_support_user():
		return
	if is_allowed_for_key_session(path):
		return
	frappe.throw(
		_("The support user's API key may only call the support endpoints, not {0}").format(path),
		frappe.PermissionError,
	)


def key_session_user(header: str | None) -> str | None:
	"""The user a valid API-key Authorization header names, or None.

	Frappe resolves API keys only inside the API handler, after the request
	hooks, so at hook time the session user is still Guest. The gate looks the
	key up itself; an invalid key is left for Frappe's own authentication.
	"""
	if not header:
		return None
	parts = header.split(" ", 1)
	if len(parts) != 2:
		return None
	scheme, credentials = parts[0].lower(), parts[1].strip()
	if scheme == "basic":
		import base64

		try:
			credentials = base64.b64decode(credentials).decode()
		except (ValueError, UnicodeDecodeError):
			return None
	elif scheme not in ("token", "bearer"):
		return None
	if ":" not in credentials:
		return None
	api_key, api_secret = credentials.split(":", 1)
	user = frappe.db.get_value("User", {"api_key": api_key, "enabled": 1}, "name")
	if not user:
		return None
	from frappe.utils.password import get_decrypted_password

	stored = get_decrypted_password("User", user, "api_secret", raise_exception=False)
	return user if stored and stored == api_secret else None


def before_request():
	"""Request hook: runs before the endpoint, with the key resolved here."""
	request = getattr(frappe.local, "request", None)
	if request is None:
		return
	# a desk session is checked whatever headers come with it (a cookie with a junk Authorization header too)
	end_revoked_session()
	header = frappe.get_request_header("Authorization")
	if not header:
		return
	cmd = (frappe.form_dict or {}).get("cmd")
	path = f"/api/method/{cmd}" if cmd else request.path
	user = key_session_user(header) or frappe.session.user
	gate(user, path, True)


# in a desk session opened by a one-time login link: the fingerprint of the API key it was opened with
SESSION_KEY = "tbo_support_key"


def key_fingerprint(api_key: str | None) -> str | None:
	"""A fingerprint of the support user's API key, kept in the sessions it opens (never the key itself)."""
	return hashlib.sha256(api_key.encode()).hexdigest()[:32] if api_key else None


def end_revoked_session() -> None:
	"""A desk session of the support user (opened by a one-time login link) holds only while the API key it
	was opened with does. Revocation takes the key and ends the sessions, but a login request still finishing
	at that moment can write its session back into Frappe's session cache, which Frappe reads first; and a new
	pairing makes a new key. So the session carries the fingerprint of its key (api.one_time_login), and a
	session whose key is gone or replaced, or that carries none, is logged out here, whatever the cache holds."""
	user = frappe.session.user
	if not user or user in ("Guest", "Administrator") or user != get_support_user():
		return
	current = key_fingerprint(frappe.db.get_value("User", user, "api_key"))
	opened_with = (getattr(frappe.session, "data", None) or {}).get(SESSION_KEY)
	if current and opened_with == current:
		return
	login_manager = getattr(frappe.local, "login_manager", None)
	if login_manager:
		login_manager.logout()
	frappe.throw(_("TBO Support's access to this site has ended."), frappe.AuthenticationError)
