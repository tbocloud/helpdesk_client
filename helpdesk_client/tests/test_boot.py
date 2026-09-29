# Copyright (c) 2026, Wahni IT Solutions Pvt. Ltd. and contributors
# For license information, please see license.txt

from unittest.mock import MagicMock, patch

from frappe.tests.utils import FrappeTestCase

from helpdesk_client.boot import set_bootinfo


def make_settings(
	enable_ticket_raising=1,
	max_recording_size=50,
	save_recording="Public",
	enable_session_replay=0,
	replay_minutes=2,
	replay_privacy="Hide numbers and typed values",
):
	settings = MagicMock()
	settings.enable_ticket_raising = enable_ticket_raising
	settings.max_recording_size = max_recording_size
	settings.save_recording = save_recording
	settings.enable_session_replay = enable_session_replay
	settings.replay_minutes = replay_minutes
	settings.replay_privacy = replay_privacy
	return settings


class TestSetBootinfo(FrappeTestCase):
	@patch("helpdesk_client.boot.frappe.get_cached_doc")
	def test_bootinfo_keys(self, mock_settings):
		mock_settings.return_value = make_settings()
		bootinfo = {}
		set_bootinfo(bootinfo)
		self.assertEqual(bootinfo["genie_support_enabled"], 1)
		self.assertEqual(bootinfo["genie_max_file_size"], 50)
		self.assertEqual(bootinfo["genie_file_type"], 0)

	@patch("helpdesk_client.boot.frappe.get_cached_doc")
	def test_private_recording_flag(self, mock_settings):
		mock_settings.return_value = make_settings(save_recording="Private")
		bootinfo = {}
		set_bootinfo(bootinfo)
		self.assertEqual(bootinfo["genie_file_type"], 1)

	@patch("helpdesk_client.boot.frappe.get_cached_doc")
	def test_replay_config_when_enabled(self, mock_settings):
		mock_settings.return_value = make_settings(
			enable_session_replay=1, replay_minutes=3, replay_privacy="Hide all text"
		)
		bootinfo = {}
		set_bootinfo(bootinfo)
		self.assertEqual(
			bootinfo["genie_replay"],
			{"enabled": True, "minutes": 3, "privacy": "Hide all text"},
		)

	@patch("helpdesk_client.boot.frappe.get_cached_doc")
	def test_replay_absent_when_disabled(self, mock_settings):
		"""Absent, not just disabled, so the desk loads no recorder at all."""
		mock_settings.return_value = make_settings(enable_session_replay=0)
		bootinfo = {}
		set_bootinfo(bootinfo)
		self.assertNotIn("genie_replay", bootinfo)

	@patch("helpdesk_client.boot.frappe.get_cached_doc")
	def test_replay_absent_when_ticket_raising_disabled(self, mock_settings):
		mock_settings.return_value = make_settings(enable_ticket_raising=0, enable_session_replay=1)
		bootinfo = {}
		set_bootinfo(bootinfo)
		self.assertNotIn("genie_replay", bootinfo)

	@patch("helpdesk_client.boot.frappe.get_cached_doc")
	def test_replay_defaults_for_unset_values(self, mock_settings):
		"""Upgraded sites have no stored value for the new fields yet."""
		mock_settings.return_value = make_settings(
			enable_session_replay=1, replay_minutes=None, replay_privacy=None
		)
		bootinfo = {}
		set_bootinfo(bootinfo)
		self.assertEqual(bootinfo["genie_replay"]["minutes"], 2)
		self.assertEqual(bootinfo["genie_replay"]["privacy"], "Hide numbers and typed values")
