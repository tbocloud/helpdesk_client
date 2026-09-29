# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Store the support user and hub URL in HDS Support Settings.

Registered sites keep support@quarkcs.com (the hub's API keys belong to it).
Sites not registered yet move to the TBO user and hub, and the old user is
disabled.
"""

import frappe

from helpdesk_client.support_user import (
	DEFAULT_HUB_URL,
	DEFAULT_SUPPORT_USER,
	LEGACY_HUB_URL,
	LEGACY_SUPPORT_USER,
)


def execute():
	settings = frappe.get_single("HDS Support Settings")
	if settings.support_user:
		return
	registered = bool(settings.client_id)
	legacy_exists = frappe.db.exists("User", LEGACY_SUPPORT_USER)
	support_user = LEGACY_SUPPORT_USER if registered and legacy_exists else DEFAULT_SUPPORT_USER
	frappe.db.set_single_value("HDS Support Settings", "support_user", support_user)

	if not registered and (settings.qcs_hub_url or LEGACY_HUB_URL) == LEGACY_HUB_URL:
		frappe.db.set_single_value("HDS Support Settings", "qcs_hub_url", DEFAULT_HUB_URL)

	if support_user == DEFAULT_SUPPORT_USER:
		from helpdesk_client.setup import _create_support_user

		_create_support_user()
		if legacy_exists:
			frappe.db.set_value("User", LEGACY_SUPPORT_USER, "enabled", 0)
