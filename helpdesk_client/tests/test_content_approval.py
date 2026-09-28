# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


def make_approval(**values):
	return frappe.get_doc(
		{
			"doctype": "Content Approval",
			"title": "Diwali offer carousel",
			"channel": "Instagram",
			"hub_post": "POST-2026-00001",
			**values,
		}
	).insert(ignore_permissions=True)


class TestContentApproval(FrappeTestCase):
	def setUp(self):
		self.addCleanup(frappe.db.rollback)

	def test_approving_records_who_and_when(self):
		approval = make_approval()
		approval.status = "Approved"
		approval.save()
		self.assertEqual(approval.decided_by, frappe.session.user)
		self.assertTrue(approval.decided_on)

	def test_changes_need_a_comment(self):
		approval = make_approval()
		approval.status = "Changes Requested"
		with self.assertRaises(frappe.ValidationError):
			approval.save()

		approval.client_comment = "Use the new logo"
		approval.save()
		self.assertEqual(approval.status, "Changes Requested")

	def test_resending_clears_previous_decision(self):
		approval = make_approval()
		approval.status = "Approved"
		approval.save()

		approval.status = "Pending"
		approval.save()
		self.assertFalse(approval.decided_by)
		self.assertFalse(approval.decided_on)
