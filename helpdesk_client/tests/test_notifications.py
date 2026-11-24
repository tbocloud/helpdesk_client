# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


class TestStatusNotifications(FrappeTestCase):
	"""Status now arrives as a Hub write over MCP rather than a local poll,
	so the notification must hang off the document, not off a sync job."""

	def make_ticket(self):
		return frappe.get_doc(
			{
				"doctype": "Support Ticket",
				"subject": "Printer offline",
				"description": "<p>offline</p>",
				"raised_by": "Administrator",
			}
		).insert(ignore_permissions=True)

	def notification_count(self, doc):
		return frappe.db.count(
			"Notification Log",
			{"document_type": "Support Ticket", "document_name": doc.name},
		)

	def test_status_change_notifies_the_raiser(self):
		doc = self.make_ticket()
		before = self.notification_count(doc)

		doc.status = "Resolved"
		doc.save(ignore_permissions=True)

		self.assertEqual(self.notification_count(doc), before + 1)

	def test_no_notification_when_status_unchanged(self):
		doc = self.make_ticket()
		doc.save(ignore_permissions=True)
		before = self.notification_count(doc)

		doc.screen_recording = "/private/files/rec.mp4"
		doc.save(ignore_permissions=True)

		self.assertEqual(self.notification_count(doc), before)

	def test_last_synced_stamped_on_status_change(self):
		doc = self.make_ticket()
		self.assertIsNone(doc.last_synced)

		doc.status = "Open"
		doc.save(ignore_permissions=True)
		doc.reload()

		self.assertIsNotNone(doc.last_synced)

	def test_client_schedules_no_poller(self):
		"""The outbound poller is gone; the crons are local: replay cleanup, the reminder to check a fix,
		the report of tickets nobody picked up (they write notices here and call nobody), and the retry
		that makes ticket recordings private (it moves files on this site)."""
		events = frappe.get_hooks("scheduler_events", app_name="helpdesk_client")
		self.assertEqual(
			dict(events),
			{
				"hourly": ["helpdesk_client.inbox.report_waiting_tickets"],
				"daily": [
					"helpdesk_client.utils.session_replay.delete_expired_session_replays",
					"helpdesk_client.inbox.remind_unconfirmed",
					"helpdesk_client.setup.make_recordings_private",
				],
			},
			f"client must schedule no poller, found: {events}",
		)


class TestWhoHears(FrappeTestCase):
	def test_administrators_own_tickets_get_their_notices(self):
		"""Phase 23 B15: on many sites Administrator is the admin's own sign-in."""
		from helpdesk_client.utils.notifications import _readers

		doc = frappe._dict(raised_by="Administrator", followers=[frappe._dict(user="Guest")])
		self.assertEqual(_readers(doc), ["Administrator"])


class TestFollowersHearTheStage(FrappeTestCase):
	def setUp(self):
		from helpdesk_client.tests.test_hub_api import ensure_user

		self.addCleanup(frappe.db.rollback)
		self.raiser = ensure_user("stage-notice-raiser@example.com")
		self.follower = ensure_user("stage-notice-follower@example.com")

	def notices(self, doc, user):
		return frappe.get_all(
			"Notification Log", filters={"for_user": user, "document_name": doc.name}, pluck="subject"
		)

	def test_a_stage_that_waits_for_the_raiser_reaches_the_followers_too(self):
		doc = frappe.get_doc(
			{
				"doctype": "Support Ticket",
				"subject": "Margins",
				"description": "<p>x</p>",
				"raised_by": self.raiser,
				"status": "Open",
				"stage": "Working on it",
				"followers": [{"user": self.follower}],
			}
		).insert(ignore_permissions=True)

		# the status stays Open: only the stage turns the ticket red
		doc.stage, doc.stage_message = "Waiting for you", "Send the invoice number"
		doc.save(ignore_permissions=True)

		raiser = self.notices(doc, self.raiser)
		self.assertEqual(len(raiser), 1)  # the one that says what is needed, not the stage one too
		self.assertIn("needs you", raiser[0])
		follower = self.notices(doc, self.follower)
		self.assertEqual(len(follower), 1)
		self.assertIn("Waiting for you", follower[0])
