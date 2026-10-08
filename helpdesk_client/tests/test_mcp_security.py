# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""The MCP endpoint answers only the hub, and its tools stay inside the switches."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

import helpdesk_client.mcp.handler  # noqa: F401  (registers the tool modules)
from helpdesk_client.mcp.auth import authenticate_request
from helpdesk_client.mcp.tools import execute_tool

OTHER_USER = "mcp-other-user@example.com"


def make_user_with_keys(email):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": "MCP Test", "send_welcome_email": 0}
		).insert(ignore_permissions=True)
	user = frappe.get_doc("User", email)
	user.api_key = frappe.generate_hash(length=15)
	user.api_secret = frappe.generate_hash(length=15)
	user.enabled = 1
	user.save(ignore_permissions=True)
	secret = frappe.utils.password.get_decrypted_password("User", email, "api_secret")
	return user.api_key, secret


class TestMcpAuth(FrappeTestCase):
	def setUp(self):
		self.addCleanup(frappe.db.rollback)
		self.addCleanup(frappe.set_user, "Administrator")

	def authenticate(self, header):
		with patch("helpdesk_client.mcp.auth.frappe.get_request_header", return_value=header):
			return authenticate_request()

	def test_other_users_keys_are_refused_even_when_valid(self):
		key, secret = make_user_with_keys(OTHER_USER)
		with self.assertRaises(frappe.AuthenticationError):
			self.authenticate(f"Token {key}:{secret}")

	def test_support_user_keys_are_accepted(self):
		frappe.db.set_single_value("HDS Support Settings", "support_user", OTHER_USER)
		key, secret = make_user_with_keys(OTHER_USER)
		self.assertEqual(self.authenticate(f"Token {key}:{secret}"), OTHER_USER)
		self.assertEqual(self.authenticate(f"Bearer {key}:{secret}"), OTHER_USER)

	def test_oauth_style_bearer_tokens_are_not_accepted(self):
		with self.assertRaises(frappe.AuthenticationError):
			self.authenticate("Bearer some-opaque-oauth-token")

	def test_oauth_module_is_gone(self):
		import importlib

		with self.assertRaises(ModuleNotFoundError):
			importlib.import_module("helpdesk_client.mcp.oauth")
		self.assertNotIn("helpdesk_client.mcp.oauth.before_request_handler", frappe.get_hooks("before_request"))


class TestToolSwitches(FrappeTestCase):
	def setUp(self):
		self.addCleanup(frappe.db.rollback)
		self.addCleanup(frappe.set_user, "Administrator")
		frappe.db.set_single_value("HDS Support Settings", "enabled", 1)
		frappe.db.set_single_value("HDS Support Settings", "allow_write_operations", 1)

	def test_disabled_support_blocks_tools_without_a_doctype(self):
		frappe.db.set_single_value("HDS Support Settings", "enabled", 0)
		result = execute_tool("get_site_info", {})
		self.assertTrue(result["isError"])
		self.assertIn("disabled", result["content"][0]["text"])

	def test_clear_cache_needs_the_write_switch(self):
		frappe.db.set_single_value("HDS Support Settings", "allow_write_operations", 0)
		result = execute_tool("clear_cache", {})
		self.assertTrue(result["isError"])
		self.assertIn("Write operations are disabled", result["content"][0]["text"])

	def test_run_doc_method_allows_only_submit_and_cancel(self):
		todo = frappe.get_doc({"doctype": "ToDo", "description": "mcp test"}).insert()
		result = execute_tool(
			"run_doc_method", {"doctype": "ToDo", "name": todo.name, "method": "rename"}
		)
		self.assertTrue(result["isError"])
		self.assertIn("not permitted", result["content"][0]["text"])
		self.assertTrue(frappe.db.exists("ToDo", todo.name))

	def test_child_table_write_is_checked_against_the_parent(self):
		# Only the parent (User) is blocked, so a refusal can come only from the parent check
		settings = frappe.get_single("HDS Support Settings")
		settings.set("blocked_doctypes", [{"doctype_name": "User"}])
		settings.set("allowed_doctypes", [])
		settings.save(ignore_permissions=True)
		row = frappe.db.get_value("Has Role", {"parent": "Administrator"}, "name")
		result = execute_tool(
			"set_value", {"doctype": "Has Role", "name": row, "fieldname": "role", "value": "Guest"}
		)
		self.assertTrue(result["isError"])
		self.assertIn("User", result["content"][0]["text"])
		created = execute_tool("create_doc", {"doctype": "Has Role", "values": {"role": "Guest"}})
		self.assertTrue(created["isError"])
		self.assertIn("child table", created["content"][0]["text"])

	def test_get_count_needs_read_permission(self):
		frappe.set_user("Guest")
		result = execute_tool("get_count", {"doctype": "User"})
		self.assertTrue(result["isError"])

	def test_refusals_are_not_written_to_error_log(self):
		frappe.db.set_single_value("HDS Support Settings", "allow_write_operations", 0)
		with patch("helpdesk_client.mcp.tools.frappe.log_error") as log_error:
			result = execute_tool("clear_cache", {})
		self.assertTrue(result["isError"])
		log_error.assert_not_called()

	def test_scheduler_flag_is_not_inverted(self):
		import json

		info = json.loads(execute_tool("get_site_info", {})["content"][0]["text"])
		expected = not frappe.utils.scheduler.is_scheduler_inactive()
		self.assertEqual(info["scheduler_enabled"], expected)
