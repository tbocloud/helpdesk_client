# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""The Support chat (TBO Copilot Phase 5): the site relays its user's messages to TBO Support, signed."""

import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk_client import chat, hub_api
from helpdesk_client.support_user import get_support_user
from helpdesk_client.tests.test_hub_api import ensure_user

USER = "chat-user@example.com"
OTHER = "chat-other@example.com"
KEY = "the-pairing-key"


def hub_says(**reply):
	response = MagicMock(status_code=200)
	response.json.return_value = {
		"enabled": True,
		"conversation": "TBO-CONV-2026-00001",
		"state": "Talking",
		"messages": [],
		**reply,
	}
	return response


class ChatCase(FrappeTestCase):
	def setUp(self):
		self.addCleanup(frappe.db.rollback)
		self.addCleanup(frappe.set_user, "Administrator")
		ensure_user(USER)
		ensure_user(OTHER)
		settings = frappe.get_single("HDS Support Settings")
		settings.update(
			{
				"enable_ticket_raising": 1,
				"enable_chat": 1,
				"client_id": "TBO-CONN-2026-00009",
				"qcs_hub_url": "https://tbo.example.com",
				"approval_key": KEY,
			}
		)
		settings.flags.ignore_mandatory = True
		settings.save(ignore_permissions=True)
		frappe.clear_document_cache("HDS Support Settings", "HDS Support Settings")
		self.addCleanup(frappe.clear_document_cache, "HDS Support Settings", "HDS Support Settings")
		self.replies = []
		self.posted = []
		patcher = patch("helpdesk_client.chat.requests.post", side_effect=self.fake_post)
		patcher.start()
		self.addCleanup(patcher.stop)

	def fake_post(self, url, data=None, headers=None, timeout=None):
		self.posted.append((url, data, headers))
		return self.replies.pop(0) if self.replies else hub_says()

	def start(self):
		frappe.set_user(USER)
		self.replies.append(
			hub_says(
				messages=[
					{
						"name": "m1",
						"direction": "Assistant",
						"kind": "Question",
						"text": "Hi, what happened?",
						"card": {"lines": ["Hi, what happened?"]},
					}
				]
			)
		)
		return chat.start(
			page_route="Form/Sales Invoice/SINV-1", ref_doctype="Sales Invoice", ref_docname="SINV-1"
		)


class TestTheRelay(ChatCase):
	def test_every_message_is_signed_with_the_derived_key_and_says_who_wrote(self):
		started = self.start()

		url, body, headers = self.posted[0]
		self.assertEqual(url, "https://tbo.example.com/api/method/helpdesk.api.copilot_conversation.message")
		key = hmac.new(KEY.encode(), b"conversation-v1", hashlib.sha256).digest()
		expected = hmac.new(
			key, f"{headers['X-TBO-Timestamp']}.{headers['X-TBO-Nonce']}.".encode() + body, hashlib.sha256
		).hexdigest()
		self.assertEqual(headers["X-TBO-Signature"], expected)
		self.assertEqual(headers["X-TBO-Connection"], "TBO-CONN-2026-00009")
		payload = json.loads(body)
		self.assertEqual((payload["action"], payload["user"]["email"]), ("start", USER))
		self.assertEqual(payload["context"]["ref_docname"], "SINV-1")
		self.assertIn("user_roles", payload["context"])
		self.assertEqual(started["messages"][0]["text"], "Hi, what happened?")
		self.assertEqual(
			frappe.db.get_value(chat.CONVERSATION, started["conversation"], "hub_conversation"),
			"TBO-CONV-2026-00001",
		)

	def test_no_chat_when_it_is_off_unpaired_signed_out_or_off_on_the_hub(self):
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			chat.start()
		frappe.set_user("Administrator")
		frappe.db.set_single_value("HDS Support Settings", "enable_chat", 0)
		frappe.clear_document_cache("HDS Support Settings", "HDS Support Settings")
		frappe.set_user(USER)
		with self.assertRaises(chat.ChatUnavailable):
			chat.start()
		frappe.set_user("Administrator")
		frappe.db.set_single_value("HDS Support Settings", "enable_chat", 1)
		frappe.clear_document_cache("HDS Support Settings", "HDS Support Settings")
		frappe.set_user(USER)
		self.replies.append(hub_says(enabled=False))
		with self.assertRaises(chat.ChatUnavailable):
			chat.start()
		self.assertFalse(frappe.db.exists(chat.CONVERSATION, {"user": USER}))

	def test_an_unreachable_hub_offers_the_form(self):
		frappe.set_user(USER)
		self.replies.append(MagicMock(status_code=503))
		with self.assertRaises(chat.ChatUnavailable):
			chat.start()


class TestTheConversation(ChatCase):
	def test_a_user_reads_and_writes_only_their_own_chat(self):
		name = self.start()["conversation"]
		frappe.set_user(OTHER)
		with self.assertRaises(frappe.PermissionError):
			chat.send(name, "hello")
		with self.assertRaises(frappe.PermissionError):
			chat.history(name)
		self.assertEqual(frappe.get_list(chat.CONVERSATION, pluck="name"), [])

	def test_the_open_chat_comes_back_until_a_new_one_is_asked_for(self):
		name = self.start()["conversation"]
		self.assertEqual(chat.start()["conversation"], name)
		self.assertNotEqual(chat.start(new=1)["conversation"], name)

	def test_only_the_users_own_private_files_go_to_the_hub(self):
		name = self.start()["conversation"]
		mine = frappe.get_doc(
			{"doctype": "File", "file_name": "mine.png", "content": b"x", "is_private": 1}
		).insert()
		frappe.set_user("Administrator")
		theirs = frappe.get_doc(
			{"doctype": "File", "file_name": "theirs.png", "content": b"y", "is_private": 1}
		).insert()
		frappe.set_user(USER)
		chat.send(
			name, "see these", files=json.dumps([{"file_url": mine.file_url}, {"file_url": theirs.file_url}])
		)
		sent = json.loads(self.posted[-1][1])["files"]
		self.assertEqual([f["file_url"] for f in sent], [mine.file_url])

	def test_a_raised_ticket_becomes_the_sites_own_ticket_without_a_second_import(self):
		name = self.start()["conversation"]
		self.replies.append(
			hub_says(
				state="Ticket raised",
				ticket="0312",
				fields={"title": "Invoice won't submit", "actual": "A margin error"},
				messages=[
					{
						"name": "m2",
						"direction": "Assistant",
						"kind": "Ticket",
						"text": "Ticket #0312 is raised.",
					}
				],
			)
		)
		with patch("helpdesk_client.utils.hub_ping.frappe.enqueue") as pinged:
			reply = chat.send(name, action="raise")
		ticket = frappe.get_doc("Support Ticket", reply["ticket"])
		self.assertEqual(
			(ticket.ticket_id, ticket.status, ticket.subject), ("0312", "Open", "Invoice won't submit")
		)
		self.assertIn("A margin error", ticket.description)
		pinged.assert_not_called()  # the hub raised it already: no "new ticket" ping
		linked = json.loads(self.posted[-1][1])
		self.assertEqual((linked["action"], linked["client_ticket"]), ("linked", ticket.name))


class TestFromTheHub(ChatCase):
	def test_post_message_is_post_only_for_the_support_user_once_and_live(self):
		name = self.start()["conversation"]
		self.assertEqual(frappe.allowed_http_methods_for_whitelisted_func.get(hub_api.post_message), ["POST"])
		with self.assertRaises(frappe.PermissionError):
			hub_api.post_message(name, "ref-1", "Working on it", "System", "Stage")
		frappe.set_user(ensure_user(get_support_user(), roles=("System Manager",)))
		with patch("helpdesk_client.hub_api.frappe.publish_realtime") as live:
			first = hub_api.post_message(
				name,
				"ref-1",
				"We are working on it.",
				"System",
				"Stage",
				json.dumps({"title": "Working on it"}),
			)
			again = hub_api.post_message(name, "ref-1", "We are working on it.", "System", "Stage")
		self.assertEqual((first["duplicate"], again["duplicate"]), (False, True))
		chats = [c for c in live.call_args_list if c.args[0] == "helpdesk_client_chat"]
		self.assertEqual(len(chats), 1)  # once, to the chat's own user
		self.assertEqual(chats[0].kwargs["user"], USER)
		self.assertEqual(chats[0].args[1]["message"]["card"]["title"], "Working on it")

	def test_the_site_says_it_can_chat(self):
		self.assertIn("chat_v1", hub_api.capabilities_info()["capabilities"])

	def test_the_desk_knows_when_the_button_opens_the_chat(self):
		from helpdesk_client.boot import set_bootinfo

		boot = frappe._dict()
		set_bootinfo(boot)
		self.assertTrue(boot["genie_chat_enabled"])
