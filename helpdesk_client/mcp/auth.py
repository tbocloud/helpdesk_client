# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""MCP request authentication.

Two header forms are accepted, both carrying the Frappe API key pair of the
hub's support user:
1. Authorization: Token <api_key>:<api_secret>
2. Authorization: Bearer <api_key>:<api_secret> (what mcp-remote sends)

Only the configured support user, or a user holding the hub role, may use
the MCP endpoint. Any other user's keys are refused even when valid, so a
leaked key of an ordinary user never opens the support tools.
"""

import frappe
from frappe import _
from frappe.utils.password import get_decrypted_password

from helpdesk_client.support_user import get_support_user

HUB_ROLE = "TBO Support Hub"


def authenticate_request():
	"""Authenticate the current request using the Authorization header.

	Returns the authenticated username.
	Raises frappe.AuthenticationError on failure.
	"""
	auth_header = frappe.get_request_header("Authorization")
	if not auth_header:
		frappe.throw(_("Missing Authorization header"), frappe.AuthenticationError)

	parts = auth_header.split(" ", 1)
	if len(parts) != 2:
		frappe.throw(_("Invalid Authorization header format"), frappe.AuthenticationError)

	auth_type = parts[0].lower()
	credentials = parts[1]

	if auth_type not in ("token", "bearer"):
		frappe.throw(_("Unsupported auth type: {0}").format(auth_type), frappe.AuthenticationError)
	return _authenticate_token(credentials)


def _authenticate_token(credentials):
	"""Authenticate using api_key:api_secret format."""
	if ":" not in credentials:
		frappe.throw(_("Credentials must be in format api_key:api_secret"), frappe.AuthenticationError)

	api_key, api_secret = credentials.split(":", 1)

	user = frappe.db.get_value("User", {"api_key": api_key, "enabled": True}, "name")
	if not user:
		frappe.throw(_("Invalid API key"), frappe.AuthenticationError)

	stored_secret = get_decrypted_password("User", user, fieldname="api_secret", raise_exception=False)
	if not stored_secret or api_secret != stored_secret:
		frappe.throw(_("Invalid API secret"), frappe.AuthenticationError)

	if not is_hub_user(user):
		frappe.throw(_("This API key may not use the support endpoint"), frappe.AuthenticationError)

	frappe.set_user(user)  # runs only after the api_key/secret pair is verified - nosemgrep
	return user


def is_hub_user(user: str) -> bool:
	"""Whether `user` is the hub's support user or holds the hub role."""
	return user == get_support_user() or HUB_ROLE in frappe.get_roles(user)
