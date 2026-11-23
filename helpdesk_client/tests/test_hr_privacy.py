# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Phase 23 B16: HR and payroll records are private by default for new connections."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk_client import inbox
from helpdesk_client.mcp import handler  # registers the tool modules
from helpdesk_client.mcp.access_control import is_hr_or_payroll
from helpdesk_client.mcp.tools import execute_tool
from helpdesk_client.patches.v15_0_7 import hr_payroll_privacy
from helpdesk_client.setup import _create_default_settings

SETTINGS = "HDS Support Settings"


def stored_value():
	rows = frappe.db.sql(
		"select `value` from `tabSingles` where `doctype` = %s and `field` = 'block_hr_payroll'", SETTINGS
	)
	return rows[0][0] if rows else None


class PrivacyCase(FrappeTestCase):
	def setUp(self):
		self.addCleanup(frappe.clear_document_cache, SETTINGS, SETTINGS)
		self.addCleanup(frappe.db.rollback)
		self.addCleanup(frappe.set_user, "Administrator")
		# nothing here commits; held all the same, so a slip can never write this site's settings for good
		hold = patch.object(frappe.db, "commit")
		hold.start()
		self.addCleanup(hold.stop)

	def keep_private(self, on: int):
		frappe.db.set_single_value(SETTINGS, "block_hr_payroll", on)
		frappe.clear_document_cache(SETTINGS, SETTINGS)


class TestTheBlock(PrivacyCase):
	def test_hr_and_payroll_doctypes_are_known(self):
		self.assertTrue(is_hr_or_payroll("Employee"))
		self.assertFalse(is_hr_or_payroll("ToDo"))
		self.assertFalse(is_hr_or_payroll("Sales Invoice"))
		if frappe.db.exists("DocType", "Salary Slip"):  # with hrms installed
			self.assertTrue(is_hr_or_payroll("Salary Slip"))

	def test_on_tbo_support_reads_no_hr_record_off_it_does(self):
		self.keep_private(1)
		refused = execute_tool("get_count", {"doctype": "Employee"})
		self.assertTrue(refused["isError"])
		self.assertIn("kept private", refused["content"][0]["text"])
		self.assertFalse(execute_tool("get_count", {"doctype": "ToDo"})["isError"])

		self.keep_private(0)
		opened = execute_tool("get_count", {"doctype": "Employee"})
		self.assertNotIn("kept private", opened["content"][0]["text"])


class TestTheDefault(PrivacyCase):
	def forget(self):
		frappe.db.sql(
			"delete from `tabSingles` where `doctype` = %s and `field` = 'block_hr_payroll'", SETTINGS
		)

	def test_a_new_install_keeps_them_private(self):
		with patch("builtins.print"):
			_create_default_settings()
		self.assertEqual(frappe.db.get_single_value(SETTINGS, "block_hr_payroll"), 1)

	def test_a_site_connected_before_keeps_its_list_and_its_admins_are_told(self):
		self.forget()
		frappe.db.set_single_value(SETTINGS, "client_id", "TBO-CONN-2026-00009")
		with patch.object(inbox, "tell") as told:
			hr_payroll_privacy.execute()
		self.assertEqual(str(stored_value()), "0")
		told.assert_called_once()
		users, subject, _message, link = told.call_args.args
		self.assertIn("Administrator", users)
		self.assertIn("HR and payroll", subject)
		self.assertEqual(link, "/app/hds-support-settings")

	def test_a_site_not_connected_yet_starts_private_and_a_choice_stays(self):
		self.forget()
		frappe.db.set_single_value(SETTINGS, "client_id", "")
		with patch.object(inbox, "tell") as told:
			hr_payroll_privacy.execute()
			self.assertEqual(str(stored_value()), "1")
			frappe.db.set_single_value(SETTINGS, "block_hr_payroll", 0)
			hr_payroll_privacy.execute()  # run again: the admin's choice stays
		self.assertEqual(str(stored_value()), "0")
		told.assert_not_called()
