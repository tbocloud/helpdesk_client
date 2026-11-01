# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Similar open tickets from colleagues (TBO Copilot Phase 14): found before a new ticket is raised, followed with
"This is my issue, add me to it"; the follower reads the ticket and its chat, the raiser answers."""

import json
from unittest.mock import MagicMock

import frappe

from helpdesk_client import chat, inbox, similar
from helpdesk_client.tests.test_chat import OTHER, USER, ChatCase, hub_says
from helpdesk_client.tests.test_inbox import hub_moves, ticket


class SimilarCase(ChatCase):
	def setUp(self):
		super().setUp()
		frappe.db.set_single_value("HDS Support Settings", "show_similar_tickets", 1)
		frappe.clear_document_cache("HDS Support Settings", "HDS Support Settings")
		frappe.set_user(OTHER)
		self.theirs = ticket(
			subject="Sales invoices blocked by the margin rule",
			description="<p>Every sales invoice with SKU-77 fails the margin rule on submit.</p>",
			raised_by=OTHER,
			ticket_id="0031",
			status="Open",
		)
		frappe.set_user(USER)

	def chat_about(self, text):
		"""A new chat that says `text` (on Sales Invoice SINV-1, as ChatCase.start)."""
		frappe.set_user(USER)
		self.replies.append(hub_says())
		name = chat.start(ref_doctype="Sales Invoice", ref_docname="SINV-1", new=1)["conversation"]
		chat.send(name, text)
		return name


class TestFindingThem(SimilarCase):
	def test_a_colleagues_open_ticket_that_looks_the_same_is_offered(self):
		name = self.chat_about("my sales invoices are blocked by the margin rule")

		rows = similar.similar(name)

		self.assertEqual([r["name"] for r in rows], [self.theirs.name])
		self.assertEqual(rows[0]["summary"], "Sales invoices blocked by the margin rule")
		self.assertEqual(rows[0]["colleagues"], 1)
		self.assertNotIn("description", rows[0])  # never what a colleague wrote

	def test_unrelated_hr_own_and_not_yet_picked_up_tickets_are_not(self):
		frappe.set_user(OTHER)
		ticket(
			subject="Salary slip margin rule blocked invoices",
			raised_by=OTHER,
			ticket_id="0032",
			status="Open",
		)
		ticket(subject="Sales invoices blocked by the margin rule", raised_by=OTHER, status="Pending")
		ticket(
			subject="Sales invoices blocked by the margin rule",
			raised_by=OTHER,
			ticket_id="0033",
			status="Closed",
		)
		frappe.set_user(USER)
		ticket(subject="Sales invoices blocked by the margin rule", ticket_id="0034", status="Open")

		name = self.chat_about("my sales invoices are blocked by the margin rule")
		self.assertEqual([r["name"] for r in similar.similar(name)], [self.theirs.name])
		self.assertEqual(similar.similar(self.chat_about("the warehouse barcode printer jams")), [])

	def test_an_hr_problem_is_never_matched(self):
		name = self.chat_about("payroll: sales invoices blocked by the margin rule")
		self.assertEqual(similar.similar(name), [])

	def test_the_site_can_switch_it_off(self):
		frappe.db.set_single_value("HDS Support Settings", "show_similar_tickets", 0)
		frappe.clear_document_cache("HDS Support Settings", "HDS Support Settings")
		name = self.chat_about("my sales invoices are blocked by the margin rule")
		self.assertEqual(similar.similar(name), [])

	def test_only_the_chats_own_user_asks(self):
		name = self.chat_about("my sales invoices are blocked by the margin rule")
		frappe.set_user(OTHER)
		with self.assertRaises(frappe.PermissionError):
			similar.similar(name)


class TestJoiningOne(SimilarCase):
	def join(self, name, reply=None):
		self.replies.append(
			reply
			or hub_says(
				state="Closed",
				messages=[
					{
						"name": "m9",
						"direction": "Assistant",
						"kind": "Text",
						"text": f"You now follow {self.theirs.name} with your colleagues.",
					}
				],
			)
		)
		return similar.join(name, self.theirs.name)

	def test_the_user_follows_it_and_tbo_support_is_told(self):
		name = self.chat_about("my sales invoices are blocked by the margin rule")

		joined = self.join(name)

		self.assertTrue(joined["told"])
		payload = json.loads(self.posted[-1][1])
		self.assertEqual((payload["action"], payload["client_ticket"]), ("joined", self.theirs.name))
		self.assertEqual(frappe.db.get_value(chat.CONVERSATION, name, "status"), "Closed")
		self.theirs.reload()
		self.assertEqual([f.user for f in self.theirs.followers], [USER])
		self.assertEqual(similar.similar(self.chat_about("sales invoices blocked by the margin rule")), [])

		frappe.set_user(OTHER)
		self.assertEqual(similar._colleagues(self.theirs.name), 2)

	def test_the_follower_reads_it_but_nothing_waits_for_them(self):
		self.join(self.chat_about("my sales invoices are blocked by the margin rule"))
		frappe.set_user("Administrator")
		hub_moves(self.theirs, status="Resolved")  # red for the one who raised it
		frappe.set_user(USER)

		data = inbox.overview()
		row = next(r for r in data["tickets"] if r["name"] == self.theirs.name)
		self.assertTrue(row["following"])
		self.assertFalse(row["confirm"])
		self.assertEqual(data["actions"], [])
		self.assertTrue(frappe.has_permission("Support Ticket", "read", self.theirs.name, user=USER))
		self.assertFalse(frappe.has_permission("Support Ticket", "write", self.theirs.name, user=USER))
		self.assertTrue(chat.open_ticket(self.theirs.name)["read_only"])
		with self.assertRaises(frappe.PermissionError):
			inbox.ticket_status(self.theirs.name)
		self.assertTrue(
			frappe.db.exists(
				"Notification Log",
				{"for_user": USER, "document_name": self.theirs.name, "subject": ["like", "%Resolved%"]},
			)
		)

	def test_the_follower_reads_the_tickets_chat_without_writing_in_it(self):
		self.join(self.chat_about("my sales invoices are blocked by the margin rule"))
		frappe.set_user("Administrator")
		theirs = frappe.get_doc(
			{
				"doctype": chat.CONVERSATION,
				"user": OTHER,
				"status": "With a person",
				"ticket": self.theirs.name,
			}
		).insert(ignore_permissions=True)
		frappe.set_user(USER)

		opened = chat.open_ticket(self.theirs.name)

		self.assertEqual(opened["conversation"], theirs.name)
		self.assertTrue(opened["read_only"])
		with self.assertRaises(frappe.PermissionError):
			chat.send(theirs.name, "me too")

	def test_with_an_older_tbo_support_the_user_still_follows_it(self):
		name = self.chat_about("my sales invoices are blocked by the margin rule")

		joined = self.join(name, MagicMock(status_code=417))

		self.assertFalse(joined["told"])
		self.assertIn("could not be told", joined["messages"][-1]["text"])
		self.assertNotEqual(frappe.db.get_value(chat.CONVERSATION, name, "status"), "Closed")
		self.theirs.reload()
		self.assertEqual([f.user for f in self.theirs.followers], [USER])

	def test_a_ticket_that_was_not_offered_cannot_be_joined(self):
		mine = ticket(subject="Sales invoices blocked by the margin rule", ticket_id="0035", status="Open")
		name = self.chat_about("my sales invoices are blocked by the margin rule")
		with self.assertRaises(frappe.PermissionError):
			similar.join(name, mine.name)
		self.assertFalse(any(b'"joined"' in body for _url, body, _headers in self.posted))
