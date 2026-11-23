# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Get help from a form (TBO Copilot Phase 14): the record and the error go to the chat, and the ticket keeps the
record; a form ticket's chat opens before TBO Support's next pull."""

import json
from unittest.mock import MagicMock, patch

import frappe

from helpdesk_client import chat, inbox
from helpdesk_client.tests.test_chat import OTHER, USER, ChatCase, hub_says
from helpdesk_client.tests.test_inbox import ticket

ERROR = "Row 7: the margin on SKU-77 is 11.0%, below the 20.0% minimum."


class TestGetHelpWithAnError(ChatCase):
	def start_with_error(self, **extra):
		frappe.set_user(USER)
		self.replies.append(
			hub_says(
				messages=[
					{
						"name": "m1",
						"direction": "Assistant",
						"kind": "Question",
						"text": "Hi. I have Sales Invoice SINV-1 and the error. Since when does this happen?",
					}
				]
			)
		)
		return chat.start(
			**{
				"page_route": "Form/Sales Invoice/SINV-1",
				"ref_doctype": "Sales Invoice",
				"ref_docname": "SINV-1",
				"shown_error": f"  {ERROR}\n",
				"error_action": "Submit",
				**extra,
			}
		)

	def test_the_error_is_the_first_message_and_tbo_support_gets_it_as_a_fact(self):
		started = self.start_with_error()

		first = f"Submit failed on Sales Invoice SINV-1: {ERROR}"
		opening = started["messages"][0]
		self.assertEqual((opening["direction"], opening["text"]), ("Customer", first))
		payload = json.loads(self.posted[-1][1])
		self.assertEqual((payload["action"], payload["text"]), ("start", first))
		self.assertEqual(payload["context"]["shown_error"], ERROR)
		self.assertEqual(payload["context"]["error_action"], "Submit")
		doc = frappe.get_doc(chat.CONVERSATION, started["conversation"])
		self.assertEqual((doc.ref_doctype, doc.ref_docname), ("Sales Invoice", "SINV-1"))

	def test_it_always_starts_a_new_chat_and_drops_an_unknown_action(self):
		open_chat = self.start()["conversation"]
		started = self.start_with_error(new=0, error_action="Delete")

		self.assertNotEqual(started["conversation"], open_chat)
		payload = json.loads(self.posted[-1][1])
		self.assertEqual(payload["context"]["error_action"], "")
		self.assertTrue(payload["text"].startswith("Error on Sales Invoice SINV-1:"))

	def test_without_an_error_nothing_extra_is_sent(self):
		self.start()
		payload = json.loads(self.posted[-1][1])
		self.assertNotIn("shown_error", payload["context"])
		self.assertEqual(payload["text"], "")

	def test_the_ticket_raised_from_the_chat_keeps_the_record(self):
		name = self.start()["conversation"]  # on Sales Invoice SINV-1
		self.replies.append(
			hub_says(
				state="Ticket raised",
				ticket="0312",
				fields={"title": "Invoice won't submit", "actual": "A margin error"},
			)
		)
		with patch("helpdesk_client.utils.hub_ping.frappe.enqueue"):
			reply = chat.send(name, action="raise")

		t = frappe.get_doc("Support Ticket", reply["ticket"])
		self.assertEqual((t.ref_doctype, t.ref_docname), ("Sales Invoice", "SINV-1"))
		self.assertEqual(inbox.ticket_card(t)["record"], {"doctype": "Sales Invoice", "name": "SINV-1"})


class TestTheSupportStrip(ChatCase):
	def test_it_lists_the_users_open_tickets_about_the_record(self):
		frappe.set_user(USER)
		about = ticket(ref_doctype="Sales Invoice", ref_docname="SINV-1", status="Open")
		ticket(ref_doctype="Sales Invoice", ref_docname="SINV-1", status="Closed")
		ticket(ref_doctype="Sales Invoice", ref_docname="SINV-2", status="Open")
		frappe.set_user("Administrator")
		ticket(ref_doctype="Sales Invoice", ref_docname="SINV-1", status="Open", raised_by=OTHER)
		frappe.set_user(USER)

		rows = inbox.for_record("Sales Invoice", "SINV-1")

		self.assertEqual([r["name"] for r in rows], [about.name])
		self.assertEqual(rows[0]["dot"], inbox.ORANGE)
		self.assertEqual(inbox.for_record("Sales Invoice", ""), [])


class TestAFormTicketsChatAtOnce(ChatCase):
	def test_a_ticket_not_picked_up_yet_asks_tbo_support_which_picks_it_up(self):
		frappe.set_user(USER)
		t = ticket()  # Pending, no TBO Support number yet
		self.replies.append(hub_says(state="With a person", ticket="0050"))

		opened = chat.open_ticket(t.name)

		self.assertFalse(opened.get("read_only"))
		self.assertTrue(opened["conversation"])
		payload = json.loads(self.posted[-1][1])
		self.assertEqual((payload["action"], payload["client_ticket"]), ("open_ticket", t.name))
		self.assertEqual(frappe.db.get_value("Support Ticket", t.name, "ticket_id"), "0050")

	def test_when_tbo_support_cannot_pick_it_up_it_stays_read_only(self):
		frappe.set_user(USER)
		t = ticket()
		self.replies.append(MagicMock(status_code=417))

		opened = chat.open_ticket(t.name)

		self.assertTrue(opened["read_only"])
		self.assertFalse(frappe.db.exists(chat.CONVERSATION, {"ticket": t.name}))
		self.assertFalse(frappe.db.get_value("Support Ticket", t.name, "ticket_id"))

	def test_without_the_chat_it_is_read_only_and_nothing_is_sent(self):
		frappe.db.set_single_value("HDS Support Settings", "enable_chat", 0)
		frappe.clear_document_cache("HDS Support Settings", "HDS Support Settings")
		frappe.set_user(USER)
		t = ticket()

		self.assertTrue(chat.open_ticket(t.name)["read_only"])
		self.assertEqual(self.posted, [])
