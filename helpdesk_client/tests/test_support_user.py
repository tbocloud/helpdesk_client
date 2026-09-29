# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

import json
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk_client.api import connect_to_hub
from helpdesk_client.patches.v15_0_2 import configurable_support_user
from helpdesk_client.support_user import (
	DEFAULT_HUB_URL,
	DEFAULT_SUPPORT_USER,
	LEGACY_HUB_URL,
	LEGACY_SUPPORT_USER,
	get_support_user,
)


class TestSupportUser(FrappeTestCase):
	def setUp(self):
		self.addCleanup(frappe.db.rollback)

	def set(self, **values):
		for field, value in values.items():
			frappe.db.set_single_value("HDS Support Settings", field, value)

	def make_legacy_user(self):
		if not frappe.db.exists("User", LEGACY_SUPPORT_USER):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": LEGACY_SUPPORT_USER,
					"first_name": "Helpdesk Support",
					"send_welcome_email": 0,
				}
			).insert(ignore_permissions=True)
		frappe.db.set_value("User", LEGACY_SUPPORT_USER, "enabled", 1)

	def test_configured_user_wins(self):
		self.set(support_user="hub@example.com")
		self.assertEqual(get_support_user(), "hub@example.com")

	def test_unset_falls_back_to_legacy_then_default(self):
		self.set(support_user="")
		self.make_legacy_user()
		self.assertEqual(get_support_user(), LEGACY_SUPPORT_USER)
		frappe.delete_doc("User", LEGACY_SUPPORT_USER, force=True, ignore_permissions=True)
		self.assertEqual(get_support_user(), DEFAULT_SUPPORT_USER)

	def test_unregistered_site_moves_to_tbo(self):
		self.make_legacy_user()
		self.set(support_user="", client_id="", qcs_hub_url=LEGACY_HUB_URL)

		configurable_support_user.execute()

		settings = frappe.get_single("HDS Support Settings")
		self.assertEqual(settings.support_user, DEFAULT_SUPPORT_USER)
		self.assertEqual(settings.qcs_hub_url, DEFAULT_HUB_URL)
		self.assertTrue(frappe.db.get_value("User", DEFAULT_SUPPORT_USER, "enabled"))
		self.assertFalse(frappe.db.get_value("User", LEGACY_SUPPORT_USER, "enabled"))

	def test_registered_site_keeps_its_user_and_hub(self):
		self.make_legacy_user()
		self.set(support_user="", client_id="hub-123", qcs_hub_url="https://hub.example.com")

		configurable_support_user.execute()

		settings = frappe.get_single("HDS Support Settings")
		self.assertEqual(settings.support_user, LEGACY_SUPPORT_USER)
		self.assertEqual(settings.qcs_hub_url, "https://hub.example.com")
		self.assertTrue(frappe.db.get_value("User", LEGACY_SUPPORT_USER, "enabled"))


class TestConnectToHub(FrappeTestCase):
	def setUp(self):
		self.addCleanup(frappe.db.rollback)
		self.addCleanup(frappe.set_user, "Administrator")
		commit = patch.object(frappe.db, "commit")
		commit.start()
		self.addCleanup(commit.stop)
		frappe.db.set_single_value("HDS Support Settings", "support_user", DEFAULT_SUPPORT_USER)
		frappe.db.set_single_value("HDS Support Settings", "client_id", "")

	def hub_says(self, status=200, body=None):
		response = MagicMock(status_code=status, text="")
		response.json.return_value = body or {"message": {"status": "connected"}}
		return patch("requests.post", return_value=response)

	def test_code_and_fresh_keys_go_to_the_hub(self):
		with self.hub_says() as post:
			result = connect_to_hub(code="K7PQ-2MXD-9R", hub_url="teams.teambackoffice.com")

		self.assertEqual(result["status"], "connected")
		url = post.call_args.args[0]
		body = post.call_args.kwargs["json"]
		self.assertEqual(url, "https://teams.teambackoffice.com/api/method/helpdesk.api.pair_client")
		self.assertEqual(body["code"], "K7PQ-2MXD-9R")
		self.assertEqual(body["support_user"], DEFAULT_SUPPORT_USER)
		user = frappe.get_doc("User", DEFAULT_SUPPORT_USER)
		self.assertEqual(user.api_key, body["api_key"])
		self.assertEqual(user.get_password("api_secret"), body["api_secret"])
		self.assertEqual(
			frappe.db.get_single_value("HDS Support Settings", "qcs_hub_url"),
			"https://teams.teambackoffice.com",
		)

	def test_hub_refusal_is_shown(self):
		refusal = {
			"_server_messages": json.dumps(
				[json.dumps({"message": "This connection code is invalid or has expired."})]
			)
		}
		with self.hub_says(status=401, body=refusal), self.assertRaises(frappe.ValidationError) as ctx:
			connect_to_hub(code="WRONG", hub_url="https://teams.teambackoffice.com")
		self.assertIn("invalid or has expired", str(ctx.exception))

	def test_plain_http_hub_is_refused(self):
		with self.hub_says() as post, self.assertRaises(frappe.ValidationError):
			connect_to_hub(code="K7PQ-2MXD-9R", hub_url="http://teams.teambackoffice.com")
		self.assertFalse(post.called)

	def test_only_system_managers_connect(self):
		if not frappe.db.exists("User", "clerk@example.com"):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": "clerk@example.com",
					"first_name": "Clerk",
					"send_welcome_email": 0,
				}
			).insert(ignore_permissions=True)
		frappe.set_user("clerk@example.com")
		with self.hub_says() as post, self.assertRaises(frappe.PermissionError):
			connect_to_hub(code="K7PQ-2MXD-9R")
		self.assertFalse(post.called)
