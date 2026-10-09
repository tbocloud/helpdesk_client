# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Stages, confirmation and visibility on the customer's own ticket."""

import json
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk_client.helpdesk_client.doctype.support_ticket import support_ticket as api
from helpdesk_client.patches.v15_0_4 import backfill_raised_by_email
from helpdesk_client.utils.support import create_ticket

OWNER = "stages-owner@example.com"
RAISER = "stages-raiser@example.com"
STRANGER = "stages-stranger@example.com"


def make_user(email):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}
		).insert(ignore_permissions=True)
	return email


def make_ticket(owner=OWNER, raised_by=RAISER, **values):
	"""A ticket `owner` created, raised for `raised_by` (both plain users without any role)."""
	frappe.set_user(owner)
	try:
		return frappe.get_doc(
			{
				"doctype": "Support Ticket",
				"subject": "Stage test",
				"description": "<p>Stage test</p>",
				"raised_by": raised_by,
				**values,
			}
		).insert(ignore_permissions=True)
	finally:
		frappe.set_user("Administrator")


class StageCase(FrappeTestCase):
	def setUp(self):
		self.addCleanup(frappe.db.rollback)
		self.addCleanup(frappe.set_user, "Administrator")
		for email in (OWNER, RAISER, STRANGER):
			make_user(email)


class TestVisibility(StageCase):
	def test_the_owner_and_the_raiser_see_the_ticket_and_nobody_else(self):
		doc = make_ticket()
		for user in (OWNER, RAISER):
			self.assertIn(doc.name, frappe.get_list("Support Ticket", pluck="name", user=user), user)
			self.assertTrue(frappe.has_permission("Support Ticket", "read", doc, user=user), user)
		self.assertNotIn(doc.name, frappe.get_list("Support Ticket", pluck="name", user=STRANGER))
		self.assertFalse(frappe.has_permission("Support Ticket", "read", doc, user=STRANGER))
		self.assertIn(doc.name, frappe.get_list("Support Ticket", pluck="name", user="Administrator"))


class TestConfirmAndReopen(StageCase):
	def test_customer_endpoints_accept_post_only(self):
		for fn in (api.request_close, api.confirm_resolution, api.reopen):
			self.assertEqual(frappe.allowed_http_methods_for_whitelisted_func.get(fn), ["POST"], fn.__name__)

	def test_the_raiser_confirms_and_the_hub_is_asked_to_close(self):
		doc = make_ticket(stage="Resolved", status="Resolved")
		frappe.set_user(STRANGER)
		with self.assertRaises(frappe.PermissionError):
			api.confirm_resolution(doc.name)
		frappe.set_user(RAISER)
		self.assertEqual(api.confirm_resolution(doc.name, "Works now")["confirmation"], "Confirmed")
		doc.reload()
		self.assertEqual(doc.customer_confirmation, "Confirmed")
		self.assertEqual(doc.confirmation_note, "Works now")
		self.assertTrue(doc.confirmed_at)
		self.assertEqual(doc.close_requested, 1)

	def test_nothing_to_confirm_before_the_ticket_is_resolved(self):
		doc = make_ticket(stage="Working on it", status="Open")
		frappe.set_user(RAISER)
		with self.assertRaises(frappe.ValidationError):
			api.confirm_resolution(doc.name)

	def test_reopen_needs_a_note_and_is_counted(self):
		doc = make_ticket(stage="Resolved", status="Resolved", close_requested=1)
		frappe.set_user(OWNER)
		with self.assertRaises(frappe.ValidationError):
			api.reopen(doc.name, "	")
		self.assertEqual(api.reopen(doc.name, "The total is still wrong")["reopen_count"], 1)
		doc.reload()
		self.assertEqual(doc.customer_confirmation, "Reopened")
		self.assertEqual(doc.reopen_requested, 1)
		self.assertEqual(doc.close_requested, 0)
		self.assertEqual(doc.confirmation_note, "The total is still wrong")

	def test_the_raiser_may_ask_to_close(self):
		doc = make_ticket(status="Open")
		frappe.set_user(RAISER)
		self.assertEqual(api.request_close(doc.name), "ok")
		self.assertEqual(frappe.db.get_value("Support Ticket", doc.name, "close_requested"), 1)


class TestNotifications(StageCase):
	def test_a_new_stage_notifies_the_raiser(self):
		doc = make_ticket(ticket_id="0042")
		doc.stage = "Working on it"
		doc.stage_message = "We found what is happening."
		doc.save(ignore_permissions=True)
		log = frappe.get_all(
			"Notification Log",
			filters={"for_user": RAISER, "document_name": doc.name},
			fields=["subject", "email_content"],
			order_by="creation desc",
			limit=1,
		)[0]
		self.assertIn("Working on it", log.subject)
		self.assertIn("#0042", log.subject)
		self.assertEqual(log.email_content, "We found what is happening.")

	def test_the_same_stage_saved_again_is_quiet(self):
		doc = make_ticket(stage="Received", stage_message="Got it")
		before = frappe.db.count("Notification Log", {"for_user": RAISER, "document_name": doc.name})
		doc.handled_by = "TBO Copilot"
		doc.save(ignore_permissions=True)
		self.assertEqual(frappe.db.count("Notification Log", {"for_user": RAISER, "document_name": doc.name}), before)


class TestContextCapture(StageCase):
	def settings(self, fallback="it@customer.example"):
		settings = MagicMock()
		settings.enable_ticket_raising = 1
		settings.enable_session_replay = 0
		settings.fallback_contact_email = fallback
		return settings

	@patch("helpdesk_client.utils.support.frappe.get_cached_doc")
	def test_create_ticket_records_where_the_user_was(self, mock_settings):
		mock_settings.return_value = self.settings()
		frappe.get_doc({"doctype": "Error Log", "method": "sales_invoice.validate", "error": "IndexError: boom"}).insert(
			ignore_permissions=True
		)
		name = create_ticket(
			"Invoice will not save",
			"<p>error</p>",
			page_route="Form/Sales Invoice/ACC-SINV-2026-00042",
			ref_doctype="Sales Invoice",
			ref_docname="ACC-SINV-2026-00042",
		)
		doc = frappe.get_doc("Support Ticket", name)
		self.assertEqual(doc.ref_doctype, "Sales Invoice")
		self.assertEqual(doc.ref_docname, "ACC-SINV-2026-00042")
		self.assertEqual(doc.page_route, "Form/Sales Invoice/ACC-SINV-2026-00042")
		self.assertIn("System Manager", json.loads(doc.user_roles))
		errors = json.loads(doc.error_logs)
		self.assertEqual(errors[0]["method"], "sales_invoice.validate")
		self.assertTrue(any(app["app"] == "helpdesk_client" for app in json.loads(doc.code_identity)))
		# Administrator has no email address, so the site's fallback contact is used
		self.assertEqual(doc.raised_by_email, "it@customer.example")
		self.assertEqual(doc.raised_by_name, "Administrator")

	@patch("helpdesk_client.utils.support.frappe.get_cached_doc")
	def test_a_normal_user_is_their_own_contact(self, mock_settings):
		mock_settings.return_value = self.settings()
		frappe.set_user(RAISER)
		name = create_ticket("Mine", "<p>mine</p>")
		self.assertEqual(frappe.db.get_value("Support Ticket", name, "raised_by_email"), RAISER)

	def test_the_patch_fills_old_tickets(self):
		doc = make_ticket(raised_by=RAISER)
		frappe.db.set_value("Support Ticket", doc.name, {"raised_by_email": None, "raised_by_name": None})
		backfill_raised_by_email.execute()
		email, full_name = frappe.db.get_value("Support Ticket", doc.name, ["raised_by_email", "raised_by_name"])
		self.assertEqual(email, RAISER)
		self.assertEqual(full_name, "stages-raiser")
