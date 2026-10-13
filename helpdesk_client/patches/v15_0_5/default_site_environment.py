# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Existing sites start as Production: every write from TBO Support then needs its signed approval.

The write list starts empty, so no write from TBO Support goes through until a
System Manager here fills it.
"""

import frappe


def execute():
	if not frappe.db.get_single_value("HDS Support Settings", "site_environment"):
		frappe.db.set_single_value("HDS Support Settings", "site_environment", "Production")
