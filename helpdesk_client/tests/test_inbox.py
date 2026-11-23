# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""The support inbox (TBO Copilot Phase 13): one chat per ticket, the dots, the actions and the reminders."""

import json
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, add_to_date, now_datetime

from helpdesk_client import boot, chat, inbox
from helpdesk_client.tests.test_chat import OTHER, USER, ChatCase, hub_says


def ticket(**values):
	return frappe.get_doc(
		{
			"doctype": "Support Ticket",
			"subject": "Stock report is empty",
			"description": "<p>The stock report shows nothing since Monday.</p>",
			"raised_by": USER,
			**values,
		}
	).insert(ignore_permissions=True)


def hub_moves(doc, **values):
	"""TBO Support changes the ticket, as hub_api.update_ticket does."""
	doc.reload()
	doc.update(values)
	doc.flags.from_hub = True
	doc.save(ignore_permissions=True)
	return doc


class TestTheDots(FrappeTestCase):
	def dot(self, **t):
		return inbox.state({"name": "SUP-X", **t})

	def test_whose_move_it_is(self):
		self.assertEqual(self.dot(status="Pending")["dot"], inbox.ORANGE)
		self.assertEqual(self.dot(status="Open", stage="Working on it")["line"], "Working on it")
		self.assertEqual(self.dot(status="Paused", status_label="Waiting on Task")["dot"], inbox.ORANGE)
		self.assertEqual(self.dot(status="Resolved")["dot"], inbox.RED)
		self.assertTrue(self.dot(status="Open", stage="Resolved")["confirm"])
		self.assertEqual(self.dot(status="Paused", status_label="Waiting on Customer")["dot"], inbox.RED)
		waiting = self.dot(status="Open", stage="Waiting for you", stage_message="Send the invoice number")
		self.assertEqual(
			(waiting["dot"], waiting["action"]), (inbox.RED, "Answer the team: Send the invoice number")
		)
		self.assertEqual(self.dot(status="Closed")["dot"], inbox.GREEN)

	def test_an_answer_counts_only_until_the_team_moves_the_ticket_again(self):
		earlier, later = add_days(now_datetime(), -2), add_days(now_datetime(), -1)
		confirmed = self.dot(
			status="Resolved", customer_confirmation="Confirmed", confirmed_at=later, last_synced=earlier
		)
		self.assertEqual((confirmed["dot"], confirmed["closed"]), (inbox.GREEN, True))
		# reopened, then fixed again: the old confirmation does not close it
		again = self.dot(
			status="Resolved", customer_confirmation="Confirmed", confirmed_at=earlier, last_synced=later
		)
		self.assertEqual(again["dot"], inbox.RED)
		reopened = self.dot(
			status="Closed", customer_confirmation="Reopened", confirmed_at=later, last_synced=earlier
		)
		self.assertEqual(reopened["dot"], inbox.ORANGE)


class TestTheInbox(ChatCase):
	def test_the_users_tickets_open_first_with_the_red_ones_as_actions(self):
		frappe.set_user(USER)
		closed = ticket(subject="Old letterhead", status="Closed")
		waiting = ticket(subject="Invoice won't submit", status="Resolved")
		working = ticket(subject="Print format margins", status="Open", stage="Working on it")
		frappe.set_user("Administrator")
		ticket(subject="Someone else's", raised_by=OTHER)
		frappe.set_user(USER)

		data = inbox.overview()

		self.assertEqual(
			[(t["name"], t["dot"]) for t in data["tickets"]],
			[(working.name, inbox.ORANGE), (waiting.name, inbox.RED), (closed.name, inbox.GREEN)],
		)
		self.assertEqual([t["name"] for t in data["actions"]], [waiting.name])
		self.assertEqual(data["actions"][0]["action"], "Check it and confirm it is sorted")
		self.assertEqual(data["tickets"][1]["summary"], "Invoice won't submit")

	def test_chats_are_listed_by_their_first_line_and_a_ticket_chat_is_not_one_of_them(self):
		name = self.start()["conversation"]
		chat.send(name, "the payroll export is slow")
		frappe.set_user("Administrator")
		t = ticket()
		frappe.db.set_value(chat.CONVERSATION, name, "ticket", t.name)
		frappe.set_user(USER)
		other = chat.start(new=1)["conversation"]
		chat.send(other, "how do I cancel an invoice?")

		data = inbox.overview()

		self.assertEqual(
			[(c["name"], c["summary"]) for c in data["chats"]], [(other, "how do I cancel an invoice?")]
		)
		self.assertEqual(data["tickets"][0]["conversation"], name)

	def test_a_ticket_chat_is_never_resumed_as_the_open_chat(self):
		name = self.start()["conversation"]
		frappe.set_user("Administrator")
		frappe.db.set_value(chat.CONVERSATION, name, {"ticket": ticket().name, "status": "With a person"})
		frappe.set_user(USER)
		self.assertNotEqual(chat.start()["conversation"], name)

	def test_whats_the_status_is_answered_here_from_the_ticket(self):
		frappe.set_user(USER)
		t = ticket(ticket_id="0042", status="Open", stage="Working on it", handled_by="Rahul")
		t.append(
			"updates",
			{
				"hub_ref": "c-1",
				"kind": "Reply",
				"message": "Checking the stock ledger now.",
				"author_name": "Rahul",
				"posted_at": now_datetime(),
			},
		)
		t.save(ignore_permissions=True)

		answer = inbox.ticket_status(t.name)

		self.assertEqual(answer["kind"], "Status")
		facts = dict(answer["card"]["facts"])
		self.assertEqual(facts["Ticket"], f"{t.name} (#0042)")
		self.assertEqual(facts["With"], "Rahul")
		self.assertIn("Checking the stock ledger now.", facts["Last update"])
		self.assertEqual(self.posted, [])  # nobody at TBO Support was asked
		frappe.set_user(OTHER)
		with self.assertRaises(frappe.PermissionError):
			inbox.ticket_status(t.name)


class TestAFormTicketsChat(ChatCase):
	def form_ticket(self, **values):
		frappe.set_user(USER)
		t = ticket(ticket_id="0042", status="Open", **values)
		t.append(
			"updates",
			{
				"hub_ref": "c-1",
				"kind": "Reply",
				"message": "Which warehouse?",
				"author_name": "Rahul",
				"posted_at": now_datetime(),
			},
		)
		t.save(ignore_permissions=True)
		return t

	def test_its_chat_starts_with_its_story_and_tbo_support_links_it(self):
		t = self.form_ticket()
		self.replies.append(hub_says(state="With a person", ticket="0042"))

		opened = chat.open_ticket(t.name)

		self.assertEqual(
			[(m["direction"], m["text"]) for m in opened["messages"]],
			[
				("Customer", "The stock report shows nothing since Monday."),
				("Agent", "Which warehouse?"),
			],
		)
		self.assertEqual(opened["ticket_state"]["name"], t.name)
		payload = json.loads(self.posted[-1][1])
		self.assertEqual((payload["action"], payload["client_ticket"]), ("open_ticket", t.name))
		self.assertEqual(chat.open_ticket(t.name)["conversation"], opened["conversation"])
		self.assertEqual(len(self.posted), 1)  # the second time it is already linked

	def test_before_tbo_support_picks_it_up_it_is_read_only_if_tbo_support_cannot_yet(self):
		# Phase 14: the site asks first (TBO Support picks the new ticket up at once); an older
		# TBO Support refuses, and the chat stays read-only until its next pull
		frappe.set_user(USER)
		t = ticket()  # Pending, no hub number yet
		self.replies.append(MagicMock(status_code=417))
		opened = chat.open_ticket(t.name)
		self.assertTrue(opened["read_only"])
		self.assertIsNone(opened["conversation"])
		self.assertEqual(json.loads(self.posted[-1][1])["action"], "open_ticket")

	def test_an_older_tbo_support_leaves_it_read_only(self):
		t = self.form_ticket()
		self.replies.append(MagicMock(status_code=417))
		opened = chat.open_ticket(t.name)
		self.assertTrue(opened["read_only"])
		self.assertFalse(frappe.db.exists(chat.CONVERSATION, {"ticket": t.name}))

	def test_only_the_raiser_opens_it(self):
		t = self.form_ticket()
		frappe.set_user(OTHER)
		with self.assertRaises(frappe.PermissionError):
			chat.open_ticket(t.name)

	def test_the_one_it_was_raised_for_reads_the_chat_its_maker_opened(self):
		t = self.form_ticket(raised_by=OTHER)  # USER made it for OTHER, and opens its chat first
		self.replies.append(hub_says(state="With a person", ticket="0042"))
		opened = chat.open_ticket(t.name)

		frappe.set_user(OTHER)
		theirs = chat.open_ticket(t.name)

		self.assertEqual(theirs["conversation"], opened["conversation"])
		self.assertTrue(theirs["read_only"])
		with self.assertRaises(frappe.PermissionError):
			chat.send(opened["conversation"], "me too")


class TestTheFixInTheChat(ChatCase):
	def setUp(self):
		super().setUp()
		frappe.set_user(USER)
		self.ticket = ticket(ticket_id="0042", status="Resolved")
		self.chat = frappe.get_doc(
			{
				"doctype": chat.CONVERSATION,
				"user": USER,
				"status": "With a person",
				"ticket": self.ticket.name,
			}
		).insert(ignore_permissions=True)

	def test_its_fixed_is_recorded_on_the_ticket_and_turns_it_green(self):
		chat.send(self.chat.name, action="fixed")
		self.ticket.reload()
		self.assertEqual((self.ticket.customer_confirmation, self.ticket.close_requested), ("Confirmed", 1))
		self.assertEqual(inbox.state(self.ticket)["dot"], inbox.GREEN)
		self.assertEqual(self.posted, [])  # TBO Support applies it once, on its next sync

	def test_a_closed_ticket_takes_no_more_messages_until_it_came_back(self):
		chat.send(self.chat.name, action="fixed")
		with self.assertRaisesRegex(frappe.ValidationError, "It came back"):
			chat.send(self.chat.name, "one more thing")

		sent = chat.send(self.chat.name, action="still_broken", note="It is empty again today")

		self.ticket.reload()
		self.assertEqual(self.ticket.customer_confirmation, "Reopened")
		self.assertEqual(sent["messages"][0]["text"], "It is empty again today")
		self.assertEqual(inbox.state(self.ticket)["dot"], inbox.ORANGE)

	def test_it_came_back_works_after_asking_to_close(self):
		from helpdesk_client.helpdesk_client.doctype.support_ticket import support_ticket

		self.ticket.db_set("status", "Open")
		support_ticket.request_close(self.ticket.name)
		self.ticket.reload()
		self.assertTrue(inbox.state(self.ticket)["closed"])

		chat.send(self.chat.name, action="still_broken", note="It is back")

		self.ticket.reload()
		self.assertEqual((self.ticket.customer_confirmation, self.ticket.close_requested), ("Reopened", 0))


class TestTheNotices(ChatCase):
	def notices(self, t):
		return frappe.get_all(
			"Notification Log",
			filters={"document_type": "Support Ticket", "document_name": t.name},
			fields=["subject", "link"],
			order_by="creation asc",
		)

	def test_turning_red_sends_one_notice_that_opens_the_chat(self):
		frappe.set_user(USER)
		t = ticket(ticket_id="0042", status="Open")
		frappe.set_user("Administrator")
		before = len(self.notices(t))

		hub_moves(t, status="Resolved")

		new = self.notices(t)[before:]
		self.assertEqual(len(new), 1)
		self.assertEqual(new[0].subject, f"{t.name} needs you: Check it and confirm it is sorted")
		self.assertEqual(new[0].link, f"/app/support-chat/{t.name}")

	def test_a_fix_waiting_for_the_check_is_brought_up_every_3_days(self):
		frappe.set_user(USER)
		waiting = ticket(status="Resolved")
		confirmed = ticket(status="Resolved", customer_confirmation="Confirmed", confirmed_at=now_datetime())
		frappe.set_user("Administrator")
		for t in (waiting, confirmed):
			t.db_set("last_synced", add_days(now_datetime(), -4))
		before = len(self.notices(waiting))

		inbox.remind_unconfirmed()
		inbox.remind_unconfirmed()  # the next day's run: too soon again

		self.assertEqual(len(self.notices(waiting)), before + 1)
		self.assertIn("Please check it and confirm it is sorted", self.notices(waiting)[-1].subject)
		self.assertEqual(self.notices(confirmed), [])

	def test_a_fix_given_again_after_a_reminder_waits_3_days_from_the_new_fix(self):
		frappe.set_user(USER)
		t = ticket(status="Resolved")
		frappe.set_user("Administrator")
		# reminded about the earlier fix 4 days ago; TBO Support moved it to Resolved again yesterday
		t.db_set(
			{
				"confirmation_reminded_at": add_days(now_datetime(), -4),
				"last_synced": add_days(now_datetime(), -1),
			}
		)
		before = len(self.notices(t))

		inbox.remind_unconfirmed()

		self.assertEqual(len(self.notices(t)), before)

	def test_the_red_button_counts_what_waits_for_the_user(self):
		frappe.set_user(USER)
		ticket(status="Resolved")
		ticket(status="Open")
		info = frappe._dict()
		boot.set_bootinfo(info)
		self.assertEqual(info.genie_actions_needed, 1)


class TestNotConnected(ChatCase):
	"""Phase 23 B8: a site that is not connected takes no ticket, and tickets nobody picked up are reported."""

	def disconnect(self):
		frappe.db.set_single_value("HDS Support Settings", "client_id", "")
		frappe.clear_document_cache("HDS Support Settings", "HDS Support Settings")

	def test_the_form_refuses_instead_of_saying_sent(self):
		from helpdesk_client.utils.support import create_ticket

		self.disconnect()
		frappe.set_user(USER)
		with self.assertRaisesRegex(frappe.ValidationError, "not connected"):
			create_ticket("Printer offline", "<p>offline</p>")
		self.assertFalse(frappe.db.exists("Support Ticket", {"raised_by": USER}))
		info = frappe._dict()
		boot.set_bootinfo(info)
		self.assertFalse(info.genie_support_connected)

	def test_a_waiting_ticket_says_it_was_not_sent(self):
		frappe.set_user(USER)
		t = ticket(status="Pending")
		self.assertEqual(inbox.state(t)["line"], "Sent to TBO Support")
		self.disconnect()
		self.assertIn("not connected", inbox.state(t)["line"])

	def test_tickets_pending_over_an_hour_are_reported_once_each_to_the_sites_admins(self):
		from helpdesk_client.support_user import get_support_user
		from helpdesk_client.tests.test_hub_api import ensure_user

		admin = ensure_user("p23-site-admin@example.com", roles=("System Manager",))
		ensure_user(get_support_user(), roles=("System Manager",))
		frappe.set_user(USER)
		old = [ticket(subject=f"Waiting {i}", status="Pending") for i in range(2)]
		fresh = ticket(subject="Just raised", status="Pending")
		picked_up = ticket(subject="Picked up", status="Open")
		frappe.set_user("Administrator")
		for t in (*old, picked_up):
			frappe.db.set_value(
				"Support Ticket",
				t.name,
				"creation",
				add_to_date(now_datetime(), hours=-2),
				update_modified=False,
			)

		with patch.object(inbox, "tell") as told:
			inbox.report_waiting_tickets()
			inbox.report_waiting_tickets()  # the next hour: already told

		self.assertEqual(told.call_count, 1)
		users, subject, reason, link, _first = told.call_args.args
		self.assertIn(admin, users)
		self.assertIn("Administrator", users)
		self.assertNotIn(get_support_user(), users)  # never TBO Support's own user
		for t in old:
			self.assertIn(t.name, subject)
			self.assertTrue(frappe.db.get_value("Support Ticket", t.name, "pending_reported_at"))
		self.assertNotIn(fresh.name, subject)
		self.assertNotIn(picked_up.name, subject)
		self.assertIn("not picked them up", reason)
		self.assertEqual(link, "/app/support-ticket?status=Pending")
