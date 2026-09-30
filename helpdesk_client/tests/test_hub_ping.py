# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

from unittest.mock import patch

import frappe
import requests
from frappe.tests.utils import FrappeTestCase

from helpdesk_client.utils import hub_ping


class TestHubPing(FrappeTestCase):
	def setUp(self):
		self.addCleanup(frappe.db.rollback)
		self.addCleanup(frappe.clear_document_cache, "HDS Support Settings", "HDS Support Settings")

	def configure(self, client_id="TBO-CONN-2026-00001"):
		for field, value in {
			"enabled": 1,
			"client_id": client_id,
			"qcs_hub_url": "https://teams.teambackoffice.com",
		}.items():
			frappe.db.set_single_value("HDS Support Settings", field, value)
		frappe.clear_document_cache("HDS Support Settings", "HDS Support Settings")

	def test_new_ticket_queues_a_ping_when_registered(self):
		self.configure()
		with patch.object(frappe, "enqueue") as enqueue:
			hub_ping.notify_hub(frappe._dict(name="SUP-1"))
		self.assertEqual(enqueue.call_args.args[0], "helpdesk_client.utils.hub_ping.ping_hub")

	def test_unregistered_site_does_not_ping(self):
		self.configure(client_id="")
		with patch.object(frappe, "enqueue") as enqueue:
			hub_ping.notify_hub(frappe._dict(name="SUP-1"))
		self.assertFalse(enqueue.called)

	def test_ping_sends_only_the_connection_id(self):
		self.configure()
		with patch("requests.post") as post:
			hub_ping.ping_hub()
		self.assertEqual(
			post.call_args.args[0],
			"https://teams.teambackoffice.com/api/method/helpdesk.api.ticket_raised",
		)
		self.assertEqual(post.call_args.kwargs["json"], {"client_id": "TBO-CONN-2026-00001"})

	def test_unreachable_hub_is_ignored(self):
		self.configure()
		with patch("requests.post", side_effect=requests.ConnectionError("down")):
			hub_ping.ping_hub()
