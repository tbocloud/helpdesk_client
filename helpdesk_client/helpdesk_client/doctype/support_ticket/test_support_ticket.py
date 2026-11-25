# Copyright (c) 2026, Wahni IT Solutions Pvt Ltd and Contributors
# See license.txt

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

USER_A = "support-ticket-a@example.com"
USER_B = "support-ticket-b@example.com"


def ensure_user(email):
	if not frappe.db.exists("Role", "Genie User"):
		frappe.get_doc({"doctype": "Role", "role_name": "Genie User", "desk_access": 1}).insert(
			ignore_permissions=True
		)

	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": email.split("@")[0],
				"send_welcome_email": 0,
				"roles": [{"role": "Genie User"}],
			}
		).insert(ignore_permissions=True)


def make_ticket(ticket_id, owner):
	"""Create a locally-named Support Ticket owned by `owner`.

	`ticket_id` is now the Helpdesk ID the Hub fills in later, not the
	record name, so callers must key off the returned doc.name.
	"""
	frappe.set_user(owner)
	doc = frappe.get_doc(
		{
			"doctype": "Support Ticket",
			"ticket_id": ticket_id,
			"subject": f"Issue {ticket_id}",
			"description": f"<p>Issue {ticket_id}</p>",
			"raised_by": owner,
		}
	).insert(ignore_permissions=True)
	frappe.set_user("Administrator")
	return doc


class TestSupportTicket(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_user(USER_A)
		ensure_user(USER_B)

	def tearDown(self):
		frappe.set_user("Administrator")
		super().tearDown()

	def test_insert_and_autoname(self):
		doc = make_ticket("HD-TEST-1", USER_A)
		self.assertTrue(doc.name.startswith("SUP-"))
		self.assertEqual(doc.ticket_id, "HD-TEST-1")
		self.assertEqual(doc.status, "Pending")

	def test_owner_cannot_see_others_tickets(self):
		mine = make_ticket("HD-TEST-2", USER_A)
		theirs = make_ticket("HD-TEST-3", USER_B)

		frappe.set_user(USER_B)
		visible = set(frappe.get_list("Support Ticket", pluck="name"))
		self.assertIn(theirs.name, visible)
		self.assertNotIn(mine.name, visible)  # forbidden row absent

	def test_system_manager_sees_all(self):
		doc = make_ticket("HD-TEST-4", USER_A)
		frappe.set_user("Administrator")
		visible = set(frappe.get_list("Support Ticket", pluck="name"))
		self.assertIn(doc.name, visible)


ERRORS = '[{"name": "e1", "method": "payroll.run", "error": "a payroll traceback", "at": "2026-11-25"}]'


def load_form(name):
	"""What the desk form gets for the ticket, as the session user."""
	from frappe.desk.form.load import getdoc

	frappe.response["docs"] = []
	getdoc("Support Ticket", name)
	return frappe.response["docs"][0]


class TestRecentErrorsStayWithTheRaiser(FrappeTestCase):
	"""A colleague who follows a ticket reads it, but not the raiser's recent errors: they may be about
	another part of the business (an invoice ticket carrying a payroll error). Recent Errors is at
	permlevel 1, read by System Managers; the raiser gets their own through the form's onload."""

	def setUp(self):
		commit = patch.object(frappe.db, "commit")
		commit.start()
		self.addCleanup(commit.stop)
		self.addCleanup(frappe.db.rollback)
		self.addCleanup(frappe.set_user, "Administrator")
		# each test's rollback takes its users too, so every test makes them
		ensure_user(USER_A)
		ensure_user(USER_B)
		self.ticket = make_ticket("HD-TEST-ERRORS", USER_A)
		frappe.db.set_value("Support Ticket", self.ticket.name, "error_logs", ERRORS)
		ticket = frappe.get_doc("Support Ticket", self.ticket.name)
		ticket.append("followers", {"user": USER_B})
		ticket.save(ignore_permissions=True)

	def test_a_follower_reads_the_ticket_but_not_the_errors(self):
		from frappe.client import get

		frappe.set_user(USER_B)
		form = load_form(self.ticket.name)
		self.assertEqual(form.subject, "Issue HD-TEST-ERRORS")
		self.assertFalse(form.get("error_logs"))
		self.assertNotIn("recent_errors", form.get("__onload") or {})
		self.assertFalse(get("Support Ticket", self.ticket.name).get("error_logs"))
		rows = frappe.get_list(
			"Support Ticket", filters={"name": self.ticket.name}, fields=["name", "error_logs"]
		)
		self.assertEqual([row.name for row in rows], [self.ticket.name])
		self.assertFalse(rows[0].get("error_logs"))

	def test_the_raiser_sees_their_own_errors_on_the_form(self):
		frappe.set_user(USER_A)
		form = load_form(self.ticket.name)
		self.assertFalse(form.get("error_logs"))
		self.assertEqual(form.get("__onload").get("recent_errors"), ERRORS)

	def test_a_system_manager_reads_the_field(self):
		from frappe.client import get

		frappe.set_user("Administrator")
		self.assertEqual(get("Support Ticket", self.ticket.name)["error_logs"], ERRORS)
		self.assertNotIn("recent_errors", load_form(self.ticket.name).get("__onload") or {})
