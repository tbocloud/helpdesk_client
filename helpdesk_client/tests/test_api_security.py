# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Hub endpoints take POST only, and public endpoints give nothing away."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk_client import api
from helpdesk_client.utils.support import attach_recording_file

OTHER_USER = "api-other-user@example.com"


class TestApiSecurity(FrappeTestCase):
	def setUp(self):
		self.addCleanup(frappe.db.rollback)

	def test_hub_endpoints_accept_post_only(self):
		for fn in (api.register_connection, api.deregister, api.rotate_credentials, api.generate_login_url):
			self.assertEqual(frappe.allowed_http_methods_for_whitelisted_func.get(fn), ["POST"], fn.__name__)

	def test_health_check_does_not_reveal_the_client_id(self):
		frappe.db.set_single_value("HDS Support Settings", "client_id", "TBO-CONN-2026-00001")
		self.assertEqual(set(api.health_check().keys()), {"status"})

	def test_support_status_is_for_system_managers(self):
		# frappe.only_for() is a no-op under frappe.flags.in_test (see test_impersonation)
		with patch("helpdesk_client.api.frappe.only_for", side_effect=frappe.PermissionError) as only_for:
			with self.assertRaises(frappe.PermissionError):
				api.get_support_status()
		only_for.assert_called_once_with("System Manager")

	def test_attach_recording_ignores_another_users_file(self):
		if not frappe.db.exists("User", OTHER_USER):
			frappe.get_doc(
				{"doctype": "User", "email": OTHER_USER, "first_name": "Other", "send_welcome_email": 0}
			).insert(ignore_permissions=True)
		ticket = frappe.get_doc(
			{"doctype": "Support Ticket", "subject": "owner check", "description": "x", "status": "Pending"}
		).insert(ignore_permissions=True)
		file = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": "other-recording.webm",
				"content": b"webm",
				"is_private": 1,
			}
		).insert(ignore_permissions=True)
		frappe.db.set_value("File", file.name, "owner", OTHER_USER, update_modified=False)

		attach_recording_file(ticket.name, file.file_url)

		self.assertFalse(frappe.db.get_value("File", file.name, "attached_to_name"))
