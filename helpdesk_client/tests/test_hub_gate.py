# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""The hub's key opens the support endpoints only; its keys can be revoked for good."""

import os
from unittest.mock import MagicMock, patch

import frappe
import requests
from frappe.tests.utils import FrappeTestCase
from frappe.utils.password import get_decrypted_password

from helpdesk_client import api, hub_gate, setup
from helpdesk_client.boot import set_bootinfo
from helpdesk_client.mcp.session import create_session, validate_session
from helpdesk_client.patches.v15_0_3 import make_recordings_private

SUPPORT = "gate-support-user@example.com"


def make_support_user_with_keys():
	if not frappe.db.exists("User", SUPPORT):
		frappe.get_doc(
			{"doctype": "User", "email": SUPPORT, "first_name": "Support", "send_welcome_email": 0}
		).insert(ignore_permissions=True)
	user = frappe.get_doc("User", SUPPORT)
	user.api_key = frappe.generate_hash(length=15)
	user.api_secret = frappe.generate_hash(length=15)
	user.save(ignore_permissions=True)
	frappe.db.set_single_value("HDS Support Settings", "support_user", SUPPORT)


class TestKeySessionGate(FrappeTestCase):
	def setUp(self):
		self.addCleanup(frappe.db.rollback)
		self.addCleanup(frappe.set_user, "Administrator")
		make_support_user_with_keys()

	def test_support_endpoints_are_allowed(self):
		for path in (
			"/api/method/helpdesk_client.mcp.handler.handle",
			"/api/method/helpdesk_client.hub_api.update_ticket",
			"/api/method/helpdesk_client.api.rotate_credentials",
			"/private/files/recording.webm",
		):
			hub_gate.gate(SUPPORT, path, has_authorization_header=True)

	def test_everything_else_is_refused_for_a_key_session(self):
		for path in ("/api/resource/User", "/api/method/frappe.client.get_list", "/app/user"):
			with self.assertRaises(frappe.PermissionError):
				hub_gate.gate(SUPPORT, path, has_authorization_header=True)

	def test_browser_sessions_and_other_users_are_not_gated(self):
		hub_gate.gate(SUPPORT, "/app/user", has_authorization_header=False)
		hub_gate.gate("someone@example.com", "/api/resource/User", has_authorization_header=True)

	def support_header(self):
		key = frappe.db.get_value("User", SUPPORT, "api_key")
		secret = get_decrypted_password("User", SUPPORT, "api_secret")
		return f"token {key}:{secret}"

	def test_the_key_is_resolved_from_the_header(self):
		# at hook time Frappe has not read the key yet, so the gate does it
		self.assertEqual(hub_gate.key_session_user(self.support_header()), SUPPORT)
		self.assertIsNone(hub_gate.key_session_user("token wrong:credentials"))
		self.assertIsNone(hub_gate.key_session_user("Bearer some-oauth-token"))
		self.assertIsNone(hub_gate.key_session_user(None))

	def test_the_hook_reads_cmd_when_present(self):
		previous_form_dict = frappe.local.form_dict
		frappe.local.request = MagicMock(path="/api/method/helpdesk_client.api.deregister")
		frappe.local.form_dict = frappe._dict(cmd="frappe.client.get_list")
		self.addCleanup(lambda: setattr(frappe.local, "request", None))
		self.addCleanup(lambda: setattr(frappe.local, "form_dict", previous_form_dict))
		# the session user is still Guest here, as in a real key request
		with patch.object(hub_gate.frappe, "get_request_header", return_value=self.support_header()):
			with self.assertRaises(frappe.PermissionError):
				hub_gate.before_request()

	def test_the_hook_lets_an_allowed_key_request_through(self):
		frappe.local.request = MagicMock(path="/api/method/helpdesk_client.api.deregister")
		self.addCleanup(lambda: setattr(frappe.local, "request", None))
		with patch.object(hub_gate.frappe, "get_request_header", return_value=self.support_header()):
			hub_gate.before_request()


class TestKeyRevocation(FrappeTestCase):
	def setUp(self):
		self.addCleanup(frappe.db.rollback)
		make_support_user_with_keys()

	def test_revoke_clears_keys_and_sessions(self):
		session = create_session(SUPPORT)
		self.assertTrue(validate_session(session))

		api.revoke_support_keys()

		self.assertFalse(frappe.db.get_value("User", SUPPORT, "api_key"))
		self.assertIsNone(get_decrypted_password("User", SUPPORT, "api_secret", raise_exception=False))
		self.assertFalse(validate_session(session))

	def test_revoke_ends_the_support_users_desk_sessions(self):
		# a login link already used opened a desk session, and that session needs no keys
		sessions = frappe.qb.DocType("Sessions")
		frappe.qb.into(sessions).columns(
			sessions.sessiondata, sessions.user, sessions.lastupdate, sessions.sid, sessions.status
		).insert(("{}", SUPPORT, frappe.utils.now(), frappe.generate_hash(), "Active")).run()

		with patch.object(api.frappe.db, "commit"):  # ending a session commits
			api.revoke_support_keys()

		left = frappe.qb.from_(sessions).select(sessions.sid).where(sessions.user == SUPPORT).run(pluck=True)
		self.assertEqual(left, [])

	def test_a_session_is_ended_by_the_id_the_table_holds(self):
		# Frappe 16 stores session ids hashed and takes the stored id as sid_hash (a plain sid would be
		# hashed again); Frappe 15 takes it as sid
		calls = []

		def v16(sid=None, user=None, reason="", *, sid_hash=None):
			calls.append(("v16", sid, sid_hash))

		def v15(sid=None, user=None, reason=""):
			calls.append(("v15", sid, None))

		api._end_session(v16, "stored", SUPPORT)
		api._end_session(v15, "stored", SUPPORT)
		self.assertEqual(calls, [("v16", None, "stored"), ("v15", "stored", None)])

	def test_a_session_committed_while_revocation_waited_is_ended_too(self):
		# CodeRabbit on #6: under REPEATABLE READ a plain read keeps this transaction's first snapshot, so a
		# login that committed on another connection after it would be missed; revocation reads the
		# sessions with a locking read, which sees it
		from helpdesk_client.tests.test_write_guard import second_connection

		sessions = frappe.qb.DocType("Sessions")
		frappe.qb.from_(sessions).select(sessions.sid).where(sessions.user == SUPPORT).run()  # the snapshot
		sid = frappe.generate_hash()
		other = second_connection()
		try:
			other.sql(
				"insert into `tabSessions` (sessiondata, user, lastupdate, sid, status) values (%s, %s, %s, %s, %s)",
				("{}", SUPPORT, frappe.utils.now(), sid, "Active"),
			)
			other.commit()  # the login, committed after this transaction's first read
			with patch.object(api.frappe.db, "commit"):
				api.revoke_support_keys()
			left = (
				frappe.qb.from_(sessions)
				.select(sessions.sid)
				.where(sessions.sid == sid)
				.for_update()
				.run(pluck=True)
			)
			self.assertEqual(left, [])
		finally:
			frappe.db.rollback()  # lets go of the row, so the other connection can remove it
			other.sql("delete from `tabSessions` where sid = %s", (sid,))
			other.commit()
			other.close()

	def test_a_login_link_redeemed_after_revocation_opens_no_session(self):
		# CodeRabbit on #6: the link is checked against the support user's own row, held until the request
		# commits, so a login and a revocation at the same moment come one after the other
		from helpdesk_client.utils import get_cache

		login_manager = MagicMock()
		self.addCleanup(setattr, frappe.local, "login_manager", getattr(frappe.local, "login_manager", None))
		frappe.local.login_manager = login_manager
		cache = get_cache()
		cache.set_value("one_time_login:revoked-link", SUPPORT, expires_in_sec=300)
		with patch.object(api.frappe.db, "commit"):
			api.revoke_support_keys()
		cache.set_value("one_time_login:revoked-link", SUPPORT, expires_in_sec=300)
		with self.assertRaises(frappe.ValidationError):
			api.one_time_login("revoked-link")
		login_manager.login_as.assert_not_called()

		make_support_user_with_keys()
		cache.set_value("one_time_login:live-link", SUPPORT, expires_in_sec=300)
		with patch.object(api.frappe.db, "get_value", wraps=frappe.db.get_value) as read:
			api.one_time_login("live-link")
		self.assertTrue(read.call_args_list[0].kwargs.get("for_update"))
		login_manager.login_as.assert_called_once_with(SUPPORT)

	def test_deregister_revokes_the_keys(self):
		frappe.db.set_single_value("HDS Support Settings", "client_id", "TBO-CONN-2026-00001")
		with patch.object(api.frappe.db, "commit"), patch.object(api, "_require_support_user"):
			api.deregister()
		self.assertFalse(frappe.db.get_value("User", SUPPORT, "api_key"))
		self.assertFalse(frappe.db.get_single_value("HDS Support Settings", "client_id"))

	def test_a_refused_pairing_leaves_no_working_keys(self):
		refused = MagicMock(status_code=403, text="no", json=lambda: {"exception": "refused"})
		with patch.object(api.frappe.db, "commit"), patch("requests.post", return_value=refused):
			with self.assertRaises(frappe.ValidationError):
				api.connect_to_hub(code="K7PQ-2MXD-9R", hub_url="https://teams.teambackoffice.com")
		self.assertFalse(frappe.db.get_value("User", SUPPORT, "api_key"))

	def test_a_pairing_that_fails_after_the_hub_registered_leaves_the_site_unpaired(self):
		def registered_then_timed_out(*args, **kwargs):
			# the hub's register_connection reached this site and committed; its answer here never came
			frappe.db.set_single_value(
				"HDS Support Settings", {"client_id": "TBO-CONN-2026-00001", "contract_active": 1}
			)
			raise requests.Timeout("read timed out")

		with (
			patch.object(api.frappe.db, "commit"),
			patch("requests.post", side_effect=registered_then_timed_out),
			self.assertRaises(frappe.ValidationError),
		):
			api.connect_to_hub(code="K7PQ-2MXD-9R", hub_url="https://teams.teambackoffice.com")

		self.assertFalse(frappe.db.get_value("User", SUPPORT, "api_key"))
		# not "Registered with Hub" with keys that no longer work: Connect to TBO Support shows again
		self.assertFalse(frappe.db.get_single_value("HDS Support Settings", "client_id"))
		self.assertFalse(frappe.db.get_single_value("HDS Support Settings", "contract_active"))

	def test_the_unpaired_site_patch_revokes_keys(self):
		frappe.db.set_single_value("HDS Support Settings", "client_id", "")
		from helpdesk_client.patches.v15_0_3 import revoke_keys_if_unpaired

		revoke_keys_if_unpaired.execute()
		self.assertFalse(frappe.db.get_value("User", SUPPORT, "api_key"))


class TestPrivateRecordings(FrappeTestCase):
	def setUp(self):
		self.addCleanup(frappe.db.rollback)

	def test_uploads_are_always_private(self):
		frappe.db.set_single_value("HDS Support Settings", "save_recording", "Public")
		frappe.clear_cache()
		bootinfo = {}
		set_bootinfo(bootinfo)
		self.assertEqual(bootinfo["genie_file_type"], 1)

	def test_the_patch_makes_existing_recordings_private(self):
		name = "old-recording-test.webm"
		paths = [frappe.get_site_path(*p, name) for p in (("public", "files"), ("private", "files"))]
		for path in paths:  # leftovers of an earlier run would make the move refuse
			if os.path.exists(path):
				os.remove(path)
		ticket = frappe.get_doc(
			{
				"doctype": "Support Ticket",
				"subject": "public recording",
				"description": "x",
				"status": "Pending",
			}
		).insert(ignore_permissions=True)
		file = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": name,
				"content": b"webm",
				"is_private": 0,
				"attached_to_doctype": "Support Ticket",
				"attached_to_name": ticket.name,
			}
		).insert(ignore_permissions=True)
		ticket.db_set("screen_recording", file.file_url)
		self.assertTrue(file.file_url.startswith("/files/"))

		with (
			patch.object(frappe.db, "commit"),  # the patch commits each file it moves
			patch(
				"frappe.log_error",
				side_effect=AssertionError("the patch logged an error instead of converting the file"),
			),
		):
			make_recordings_private.execute()

		file.reload()
		self.assertEqual(file.is_private, 1)
		self.assertTrue(file.file_url.startswith("/private/files/"))
		self.assertEqual(
			frappe.db.get_value("Support Ticket", ticket.name, "screen_recording"), file.file_url
		)

		# the insert and the move each registered an undo for the test's rollback;
		# the second would look for a file the first already removed
		frappe.db.after_rollback.reset()
		for path in paths:
			if os.path.exists(path):
				os.remove(path)

	def test_a_recording_that_cannot_be_moved_never_stops_a_migrate(self):
		# a file that cannot be moved (a permission error on disk, say) is rolled back, logged and stays
		# public for now; the daily job tries it again, and the customer's migrate (their deploy) goes on
		unmovable = frappe._dict(name="unmovable-recording", file_url="/files/unmovable-recording.webm")
		gone = frappe._dict(name="gone-recording", file_url="/files/gone-recording.webm")

		def get_doc(doctype, name):
			raise FileNotFoundError(name) if name == gone.name else OSError("Permission denied")

		with (
			patch.object(setup.frappe, "get_all", return_value=[unmovable, gone]),
			patch.object(setup.frappe, "get_doc", side_effect=get_doc),
			patch.object(setup.frappe, "log_error") as logged,
			patch.object(frappe.db, "rollback") as rolled_back,
			patch.object(frappe.db, "commit") as committed,
		):
			self.assertEqual(setup.make_recordings_private(), ["unmovable-recording"])
			# what was done before is committed first, so a rollback undoes only one file's change;
			# a file gone from disk is rolled back too, and not logged
			self.assertEqual(committed.call_count, 2)  # first, then the file it logged
			self.assertEqual(rolled_back.call_count, 2)
			self.assertEqual(logged.call_count, 1)
			make_recordings_private.execute()  # the patch finishes all the same
		daily = frappe.get_hooks("scheduler_events").get("daily") or []
		self.assertIn("helpdesk_client.setup.make_recordings_private", daily)
		self.assertNotIn("helpdesk_client.setup.make_recordings_private", frappe.get_hooks("after_migrate"))
