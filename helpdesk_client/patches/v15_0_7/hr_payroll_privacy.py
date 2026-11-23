# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Phase 23 B16: HR and payroll records are private by default for new connections.

A site connected to TBO Support before this version keeps what it had (TBO Support could read them), and its
System Managers get a note saying how to make them private. A site not connected yet starts private, as a new
install does.
"""

import frappe
from frappe import _

FIELD = "block_hr_payroll"


def execute():
	stored = frappe.db.sql(
		"select `value` from `tabSingles` where `doctype` = %s and `field` = %s",
		("HDS Support Settings", FIELD),
	)
	if stored:
		return  # chosen already
	connected = bool(frappe.db.get_single_value("HDS Support Settings", "client_id"))
	frappe.db.set_single_value("HDS Support Settings", FIELD, 0 if connected else 1)
	if connected:
		tell_the_admins()


def tell_the_admins():
	from helpdesk_client import inbox

	inbox.tell(
		inbox.site_admins(),
		_("TBO Support can read HR and payroll records on this site"),
		_(
			"New connections keep HR and payroll private. To do the same here, tick Keep HR and payroll private in HDS Support Settings; this site's own list of blocked doctypes is unchanged."
		),
		"/app/hds-support-settings",
	)
