# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, now_datetime

from helpdesk_client.utils.session_replay import (
	DIAGNOSTICS_FILE_NAME,
	REPLAY_FILE_NAME,
	attach_session_file,
	delete_expired_session_replays,
)


def make_ticket(status="Pending", days_ago=0):
	doc = frappe.get_doc(
		{
			"doctype": "Support Ticket",
			"subject": "Replay retention",
			"description": "<p>replay</p>",
			"raised_by": "Administrator",
		}
	).insert(ignore_permissions=True)
	frappe.db.set_value(
		"Support Ticket",
		doc.name,
		{"status": status, "modified": add_days(now_datetime(), -days_ago)},
		update_modified=False,
	)
	return doc.name


def make_file(file_name, content):
	return frappe.get_doc(
		{
			"doctype": "File",
			"file_name": file_name,
			"content": content,
			"is_private": 1,
		}
	).insert(ignore_permissions=True)


def attach_replay_files(ticket):
	"""Attach a replay, a diagnostics and an unrelated screenshot File."""
	token = frappe.generate_hash(length=10)
	replay = make_file(REPLAY_FILE_NAME, f"replay-{token}")
	diagnostics = make_file(DIAGNOSTICS_FILE_NAME, f"diagnostics-{token}")
	screenshot = make_file("screenshot.png", f"png-{token}")
	attach_session_file(ticket, replay.file_url, REPLAY_FILE_NAME)
	attach_session_file(ticket, diagnostics.file_url, DIAGNOSTICS_FILE_NAME)
	frappe.db.set_value(
		"File",
		screenshot.name,
		{"attached_to_doctype": "Support Ticket", "attached_to_name": ticket},
	)
	return replay.name, diagnostics.name, screenshot.name


class TestReplaySettingsValidation(FrappeTestCase):
	def make_settings(self, minutes, enabled=1):
		return frappe.get_doc(
			{
				"doctype": "HDS Support Settings",
				"enable_session_replay": enabled,
				"replay_minutes": minutes,
			}
		)

	def test_minutes_within_range_pass(self):
		for minutes in (1, 2, 5):
			self.make_settings(minutes).validate()

	def test_minutes_out_of_range_rejected(self):
		for minutes in (0, 6, -1):
			with self.assertRaises(frappe.ValidationError):
				self.make_settings(minutes).validate()

	def test_minutes_ignored_while_disabled(self):
		self.make_settings(0, enabled=0).validate()


class TestAttachSessionFile(FrappeTestCase):
	def test_file_gets_contract_name_even_when_frappe_renamed_it(self):
		"""A second upload of the same name is stored suffixed on disk, but
		the hub finds the file by its exact name."""
		ticket = make_ticket()
		token = frappe.generate_hash(length=10)
		make_file(REPLAY_FILE_NAME, f"first-{token}")
		second = make_file(REPLAY_FILE_NAME, f"second-{token}")

		attach_session_file(ticket, second.file_url, REPLAY_FILE_NAME)

		second.reload()
		self.assertEqual(second.file_name, REPLAY_FILE_NAME)
		self.assertEqual(second.attached_to_doctype, "Support Ticket")
		self.assertEqual(second.attached_to_name, ticket)

	def test_another_users_upload_is_not_attached(self):
		ticket = make_ticket()
		other = make_file(REPLAY_FILE_NAME, f"other-{frappe.generate_hash(length=10)}")
		frappe.db.set_value("File", other.name, "owner", "someone.else@example.com")

		attach_session_file(ticket, other.file_url, REPLAY_FILE_NAME)

		self.assertFalse(frappe.db.get_value("File", other.name, "attached_to_name"))


class TestReplayRetention(FrappeTestCase):
	def test_deletes_only_old_finished_tickets_replay_files(self):
		old_closed = attach_replay_files(make_ticket("Closed", days_ago=31))
		old_resolved = attach_replay_files(make_ticket("Resolved", days_ago=45))
		recent_closed = attach_replay_files(make_ticket("Closed", days_ago=5))
		old_open = attach_replay_files(make_ticket("Open", days_ago=60))

		delete_expired_session_replays()

		def exists(name):
			return frappe.db.exists("File", name)

		for replay, diagnostics, screenshot in (old_closed, old_resolved):
			self.assertFalse(exists(replay))
			self.assertFalse(exists(diagnostics))
			self.assertTrue(exists(screenshot), "other attachments must be kept")

		for kept in (recent_closed, old_open):
			for name in kept:
				self.assertTrue(exists(name))
