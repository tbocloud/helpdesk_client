# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""hub_api: what the hub writes on the customer's ticket and reads back."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime

from helpdesk_client import api, hub_api
from helpdesk_client.support_user import get_support_user

RAISER = "hub-api-raiser@example.com"


def ensure_user(email, roles=()):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": email.split("@")[0],
				"send_welcome_email": 0,
				"roles": [{"role": r} for r in roles],
			}
		).insert(ignore_permissions=True)
	return email


def make_ticket(**values):
	return frappe.get_doc(
		{
			"doctype": "Support Ticket",
			"subject": "Hub API",
			"description": "<p>Hub API</p>",
			"raised_by": RAISER,
			**values,
		}
	).insert(ignore_permissions=True)


def notifications(ticket):
	return frappe.get_all(
		"Notification Log",
		filters={"for_user": RAISER, "document_name": ticket},
		fields=["subject"],
		order_by="creation desc",
	)


class HubApiCase(FrappeTestCase):
	def setUp(self):
		self.addCleanup(frappe.db.rollback)
		self.addCleanup(frappe.set_user, "Administrator")
		ensure_user(RAISER)
		self.support_user = ensure_user(get_support_user(), roles=("System Manager",))
		self.ticket = make_ticket()
		frappe.set_user(self.support_user)


class TestAccess(HubApiCase):
	def test_endpoints_accept_post_only(self):
		for fn in (
			hub_api.update_ticket,
			hub_api.add_update,
			hub_api.post_reply,
			hub_api.get_ticket_changes,
			hub_api.capabilities,
		):
			self.assertEqual(frappe.allowed_http_methods_for_whitelisted_func.get(fn), ["POST"], fn.__name__)

	def test_only_the_support_user_may_call(self):
		frappe.set_user("Administrator")
		with self.assertRaises(frappe.PermissionError):
			hub_api.update_ticket(self.ticket.name, {"ticket_id": "0042"})
		frappe.set_user(RAISER)
		with self.assertRaises(frappe.PermissionError):
			hub_api.get_ticket_changes(str(now_datetime()))


class TestUpdateTicket(HubApiCase):
	def test_allowed_fields_are_applied_and_the_status_is_mapped(self):
		result = hub_api.update_ticket(
			self.ticket.name,
			{"ticket_id": "0042", "status": "Waiting on Task", "priority": "High", "stage": "Working on it", "owner": "x", "subject": "hacked"},
		)
		self.assertEqual(result["applied"], ["ticket_id", "status_label", "status", "priority", "stage"])
		self.assertEqual(result["ignored"], ["owner", "subject"])
		self.ticket.reload()
		self.assertEqual(self.ticket.status, "Paused")
		self.assertEqual(self.ticket.status_label, "Waiting on Task")
		self.assertEqual(self.ticket.subject, "Hub API")
		self.assertTrue(any("Paused" in n.subject for n in notifications(self.ticket.name)))

	def test_an_unchanged_update_is_quiet(self):
		hub_api.update_ticket(self.ticket.name, {"ticket_id": "0042", "status": "Open"})
		before = len(notifications(self.ticket.name))
		result = hub_api.update_ticket(self.ticket.name, {"ticket_id": "0042", "status": "Open"})
		self.assertEqual(result["applied"], [])
		self.assertEqual(len(notifications(self.ticket.name)), before)

	def test_an_unknown_status_keeps_the_old_one(self):
		result = hub_api.update_ticket(self.ticket.name, {"status": "Under Review"})
		self.assertEqual(result["applied"], ["status_label"])
		self.assertEqual(result["ignored"], ["status"])
		self.assertEqual(frappe.db.get_value("Support Ticket", self.ticket.name, "status"), "Pending")
		self.assertEqual(frappe.db.get_value("Support Ticket", self.ticket.name, "status_label"), "Under Review")

	def test_values_may_arrive_as_a_json_string(self):
		result = hub_api.update_ticket(self.ticket.name, '{"priority": "Low"}')
		self.assertEqual(result["applied"], ["priority"])


class TestUpdatesAndReplies(HubApiCase):
	def test_a_stage_update_is_added_once_and_moves_the_ticket(self):
		first = hub_api.add_update(self.ticket.name, "TBO-RUN-1:Working on it:1", "Working on it", "We found it")
		again = hub_api.add_update(self.ticket.name, "TBO-RUN-1:Working on it:1", "Working on it", "We found it")
		self.assertEqual((first["duplicate"], again["duplicate"]), (False, True))
		self.ticket.reload()
		self.assertEqual(len(self.ticket.updates), 1)
		self.assertEqual((self.ticket.stage, self.ticket.stage_message), ("Working on it", "We found it"))
		self.assertIn("Working on it", notifications(self.ticket.name)[0].subject)

	def test_a_system_entry_does_not_touch_the_stage(self):
		hub_api.add_update(self.ticket.name, "sys-1", message="Fix merged", kind="System")
		self.ticket.reload()
		self.assertFalse(self.ticket.stage)
		self.assertEqual(self.ticket.updates[0].kind, "System")

	def test_an_unknown_stage_or_kind_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			hub_api.add_update(self.ticket.name, "x-1", "Shipped", "no")
		with self.assertRaises(frappe.ValidationError):
			hub_api.add_update(self.ticket.name, "x-2", "", "no", kind="Whisper")

	def test_a_reply_becomes_one_comment_and_notifies_the_raiser(self):
		first = hub_api.post_reply(self.ticket.name, "COMM-0001", "<p>We fixed it.</p>", "Sara")
		again = hub_api.post_reply(self.ticket.name, "COMM-0001", "<p>We fixed it.</p>", "Sara")
		self.assertTrue(again["duplicate"])
		comments = frappe.get_all(
			"Comment",
			filters={"reference_doctype": "Support Ticket", "reference_name": self.ticket.name, "comment_type": "Comment"},
			fields=["name", "owner", "comment_by"],
		)
		self.assertEqual(len(comments), 1)
		self.assertEqual(comments[0].owner, self.support_user)
		self.assertEqual(comments[0].name, first["comment"])
		self.ticket.reload()
		self.assertEqual((self.ticket.updates[0].kind, self.ticket.updates[0].message), ("Reply", "We fixed it."))
		self.assertIn("Support replied", notifications(self.ticket.name)[0].subject)


class TestChanges(HubApiCase):
	def test_changes_since_a_cursor(self):
		cursor = str(add_to_date(now_datetime(), seconds=-1))
		frappe.db.set_value("Support Ticket", self.ticket.name, "modified", add_to_date(now_datetime(), hours=-1), update_modified=False)
		changed = make_ticket(subject="Changed")
		changed.customer_confirmation = "Reopened"
		changed.confirmation_note = "still wrong"
		changed.reopen_requested = 1
		changed.save(ignore_permissions=True)
		result = hub_api.get_ticket_changes(cursor)
		names = [t["name"] for t in result["tickets"]]
		self.assertIn(changed.name, names)
		self.assertNotIn(self.ticket.name, names)
		row = next(t for t in result["tickets"] if t["name"] == changed.name)
		self.assertEqual((row["customer_confirmation"], row["reopen_requested"]), ("Reopened", 1))
		self.assertTrue(result["server_time"])
		self.assertEqual(hub_api.get_ticket_changes(result["server_time"])["tickets"], [])

	def test_a_bad_cursor_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			hub_api.get_ticket_changes("")


class TestCapabilities(HubApiCase):
	def test_the_client_advertises_hub_api(self):
		self.assertIn("hub_api_v1", hub_api.capabilities()["capabilities"])

	def test_registration_advertises_it_too(self):
		frappe.db.set_single_value("HDS Support Settings", "enabled", 1)
		frappe.db.set_single_value("HDS Support Settings", "qcs_hub_url", "https://hub.example")
		with patch.object(frappe.db, "commit"):
			result = api.register_connection("https://hub.example", "TBO-CONN-2026-00009")
		self.assertIn("hub_api_v1", result["capabilities"])
		self.assertTrue(result["client_version"])
