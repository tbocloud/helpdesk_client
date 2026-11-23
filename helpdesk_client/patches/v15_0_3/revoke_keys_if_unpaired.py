# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""A site that is not paired with a hub must not hold working hub keys."""

import frappe


def execute():
	if frappe.db.get_single_value("HDS Support Settings", "client_id"):
		return
	from helpdesk_client.api import revoke_support_keys

	revoke_support_keys()
