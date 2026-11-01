# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""TBO Copilot Phase 14: existing sites get the new support chat settings at their defaults.

Without a stored value, the first save of the settings would store a Check as 0 and switch similar tickets off.
"""

import frappe

DEFAULTS = {"show_similar_tickets": 1, "max_recording_minutes": 3}


def execute():
	stored = set(
		frappe.db.sql(
			"select `field` from `tabSingles` where `doctype` = %s", "HDS Support Settings", pluck=True
		)
	)
	for field, value in DEFAULTS.items():
		if field not in stored:
			frappe.db.set_single_value("HDS Support Settings", field, value)
