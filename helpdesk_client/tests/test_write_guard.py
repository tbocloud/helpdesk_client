# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""The guard on writes from TBO Support: this site's write list, its never list, the
hub's signed approval, the record as it was checked, and the change log."""

import json
import time
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk_client.mcp import (
	handler,  # also registers the tool modules
	write_guard,
)
from helpdesk_client.mcp.tools import execute_tool

KEY = "test-approval-key-for-the-guard"
CHANGE_SET = "TBO-CHG-2026-00001"


def hold_commits(case):
	"""Nothing a test does reaches the site: the tools' own commits are held, then all is rolled back."""
	commit = patch.object(frappe.db, "commit")
	commit.start()
	case.addCleanup(commit.stop)
	case.addCleanup(frappe.db.rollback)


def approval(records, key=KEY, expires_in=600):
	return write_guard.sign_approval(
		{
			"v": 1,
			"change_set": CHANGE_SET,
			"ticket": "SUP-2026-00099",
			"approved_by": "senior@example.com",
			"approved_at": "2026-10-13 10:00:00",
			"exp": time.time() + expires_in,
			"records": records,
		},
		key,
	)


def text(result) -> str:
	return result["content"][0]["text"]


def log_rows(name):
	return frappe.get_all(
		"HDS Change Log",
		filters={"reference_name": name},
		fields=["status", "action", "approved_by", "change_set", "old_values", "new_values", "error"],
		order_by="creation asc",
	)


class GuardCase(FrappeTestCase):
	environment = "Production"

	def setUp(self):
		hold_commits(self)
		self.addCleanup(frappe.set_user, "Administrator")
		settings = frappe.get_single("HDS Support Settings")
		settings.enabled = 1
		settings.allow_write_operations = 1
		settings.site_environment = self.environment
		settings.approval_key = KEY
		settings.set("blocked_doctypes", [])
		settings.set("allowed_doctypes", [])
		settings.set("write_doctypes", [{"doctype_name": "ToDo", "may_update": 1, "may_create": 1}])
		settings.save(ignore_permissions=True)
		self.todo = frappe.get_doc(
			{"doctype": "ToDo", "description": "write guard test", "priority": "Low"}
		).insert(ignore_permissions=True)

	def allow(self, doctype, **flags):
		settings = frappe.get_single("HDS Support Settings")
		settings.append("write_doctypes", {"doctype_name": doctype, "may_update": 1, **flags})
		settings.save(ignore_permissions=True)

	def update(self, values, expect, name=None, item="ITEM-1", rows=None):
		change = {
			"item": item,
			"action": "update",
			"doctype": "ToDo",
			"name": name or self.todo.name,
			"values": values,
		}
		if rows:
			change["rows"] = rows
		return change, {"values": expect, "rows": {}}

	def signed(self, change, expect=None):
		parsed = write_guard.parse_change(change)
		return approval(
			[
				{
					"item": parsed["item"],
					"doctype": parsed["doctype"],
					"name": parsed["name"],
					"action": parsed["action"],
					"digest": write_guard.change_digest(parsed, expect),
				}
			]
		)


class TestTheApproval(GuardCase):
	def test_a_production_write_needs_the_hubs_signed_approval(self):
		refused = execute_tool(
			"set_value", {"doctype": "ToDo", "name": self.todo.name, "fieldname": "priority", "value": "High"}
		)
		self.assertTrue(refused["isError"])
		self.assertIn("signed approval", text(refused))
		self.assertEqual(frappe.db.get_value("ToDo", self.todo.name, "priority"), "Low")

		token = approval([{"doctype": "ToDo", "name": self.todo.name, "action": "update"}])
		done = execute_tool(
			"set_value",
			{
				"doctype": "ToDo",
				"name": self.todo.name,
				"fieldname": "priority",
				"value": "High",
				"approval": token,
			},
		)
		self.assertFalse(done["isError"], text(done))
		self.assertEqual(frappe.db.get_value("ToDo", self.todo.name, "priority"), "High")

		rows = log_rows(self.todo.name)
		self.assertEqual([row.status for row in rows], ["Refused", "Applied"])
		self.assertEqual((rows[1].approved_by, rows[1].change_set), ("senior@example.com", CHANGE_SET))
		self.assertEqual(json.loads(rows[1].old_values), {"priority": "Low"})
		self.assertEqual(json.loads(rows[1].new_values), {"priority": "High"})

	def test_an_approval_covers_only_its_records_its_action_and_its_time(self):
		other = frappe.get_doc({"doctype": "ToDo", "description": "another"}).insert(ignore_permissions=True)
		record = {"doctype": "ToDo", "name": self.todo.name, "action": "update"}
		cases = [
			("does not cover", approval([{**record, "name": other.name}])),
			("does not cover", approval([{**record, "action": "create"}])),
			("expired", approval([record], expires_in=-5)),
			("not valid", approval([record], key="another-key")),
		]
		for reason, token in cases:
			result = execute_tool(
				"set_value",
				{
					"doctype": "ToDo",
					"name": self.todo.name,
					"fieldname": "priority",
					"value": "High",
					"approval": token,
				},
			)
			self.assertTrue(result["isError"], reason)
			self.assertIn(reason, text(result))
		self.assertEqual(frappe.db.get_value("ToDo", self.todo.name, "priority"), "Low")

	def test_a_tampered_approval_is_refused(self):
		token = approval([{"doctype": "ToDo", "name": self.todo.name, "action": "update"}])
		body, _sep, signature = token.partition(".")
		forged = write_guard._b64(
			json.dumps({**json.loads(write_guard._unb64(body)), "approved_by": "someone"}).encode()
		)
		result = execute_tool(
			"set_value",
			{
				"doctype": "ToDo",
				"name": self.todo.name,
				"fieldname": "priority",
				"value": "High",
				"approval": f"{forged}.{signature}",
			},
		)
		self.assertTrue(result["isError"])
		self.assertIn("not valid", text(result))

	def test_a_site_without_an_approval_key_takes_no_write(self):
		from frappe.utils.password import remove_encrypted_password

		remove_encrypted_password("HDS Support Settings", "HDS Support Settings", "approval_key")
		token = approval([{"doctype": "ToDo", "name": self.todo.name, "action": "update"}])
		result = execute_tool(
			"set_value",
			{
				"doctype": "ToDo",
				"name": self.todo.name,
				"fieldname": "priority",
				"value": "High",
				"approval": token,
			},
		)
		self.assertIn("connect it to TBO Support again", text(result))


class TestTheLists(GuardCase):
	environment = "Sandbox"  # no approval needed: only the lists decide

	def test_only_doctypes_on_the_write_list_and_only_their_actions(self):
		note = execute_tool("create_doc", {"doctype": "Note", "values": {"title": "guard"}})
		self.assertIn("not on this site's write list", text(note))

		self.allow("Note")  # updates only
		note = execute_tool("create_doc", {"doctype": "Note", "values": {"title": "guard"}})
		self.assertIn("does not let TBO Support create Note", text(note))

		todo = execute_tool("create_doc", {"doctype": "ToDo", "values": {"description": "allowed"}})
		self.assertFalse(todo["isError"], text(todo))

		deleted = execute_tool("delete_doc", {"doctype": "ToDo", "name": self.todo.name})
		self.assertIn("may not delete", text(deleted))
		self.assertTrue(frappe.db.exists("ToDo", self.todo.name))

	def test_the_never_list_wins_over_the_write_list(self):
		self.allow("User")
		result = execute_tool(
			"set_value", {"doctype": "User", "name": "Administrator", "fieldname": "bio", "value": "x"}
		)
		self.assertIn("never changes User", text(result))

	def test_the_write_switch_still_comes_first(self):
		frappe.db.set_single_value("HDS Support Settings", "allow_write_operations", 0)
		result = execute_tool(
			"set_value", {"doctype": "ToDo", "name": self.todo.name, "fieldname": "priority", "value": "High"}
		)
		self.assertIn("Write operations are disabled", text(result))

	def test_refusals_are_in_the_change_log_and_not_in_the_error_log(self):
		errors = frappe.db.count("Error Log")
		execute_tool("delete_doc", {"doctype": "ToDo", "name": self.todo.name})
		self.assertEqual(frappe.db.count("Error Log"), errors)
		self.assertEqual([row.status for row in log_rows(self.todo.name)], ["Refused"])


class TestCheckChange(GuardCase):
	def check(self, change):
		result = execute_tool("check_change", {"change": change})
		self.assertFalse(result["isError"], text(result))
		return json.loads(text(result))

	def test_it_writes_nothing_and_returns_the_current_values(self):
		found = self.check(
			{"doctype": "ToDo", "name": self.todo.name, "values": {"priority": "High", "status": "Closed"}}
		)
		self.assertTrue(found["ok"], found["problems"])
		self.assertEqual(found["current"]["values"], {"priority": "Low", "status": "Open"})
		self.assertEqual(frappe.db.get_value("ToDo", self.todo.name, "priority"), "Low")
		self.assertFalse(log_rows(self.todo.name))

	def test_it_names_each_problem(self):
		found = self.check(
			{
				"doctype": "ToDo",
				"name": self.todo.name,
				"values": {
					"priority": "Urgent",
					"no_such_field": 1,
					"assigned_by_full_name": "x",
					"allocated_to": "nobody@example.com",
					"date": "not a date",
				},
			}
		)
		self.assertFalse(found["ok"])
		problems = " | ".join(found["problems"])
		for expected in (
			"priority must be one of",
			"has no field no_such_field",
			"assigned_by_full_name is read-only",
			"names no User called nobody@example.com",
			"date cannot hold",
		):
			self.assertIn(expected, problems)

	def test_it_says_what_the_guard_would_refuse(self):
		found = self.check({"doctype": "Note", "action": "create", "values": {"title": "x"}})
		self.assertFalse(found["ok"])
		self.assertIn("not on this site's write list", " ".join(found["problems"]))

	def test_a_new_record_needs_its_mandatory_fields(self):
		found = self.check({"doctype": "ToDo", "action": "create", "values": {"priority": "High"}})
		self.assertIn("A new ToDo needs description", " ".join(found["problems"]))

	def test_blocked_doctypes_are_not_even_read(self):
		settings = frappe.get_single("HDS Support Settings")
		settings.set("blocked_doctypes", [{"doctype_name": "ToDo"}])
		settings.save(ignore_permissions=True)
		result = execute_tool("check_change", {"change": {"doctype": "ToDo", "name": self.todo.name}})
		self.assertTrue(result["isError"])
		self.assertIn("blocked", text(result))


class TestApplyChange(GuardCase):
	def apply(self, change, expect, token=None):
		arguments = {"change": change, "approval": token or self.signed(change, expect)}
		if expect is not None:
			arguments["expect"] = expect
		return execute_tool("apply_change", arguments)

	def test_an_approved_change_is_applied_noted_and_logged(self):
		change, expect = self.update({"priority": "High"}, {"priority": "Low"})
		result = self.apply(change, expect)

		self.assertFalse(result["isError"], text(result))
		self.assertEqual(frappe.db.get_value("ToDo", self.todo.name, "priority"), "High")
		note = frappe.get_all(
			"Comment",
			filters={"reference_doctype": "ToDo", "reference_name": self.todo.name, "comment_type": "Info"},
			pluck="content",
		)
		self.assertTrue(any("for ticket SUP-2026-00099, approved by senior@example.com" in n for n in note))
		self.assertTrue(any("priority: Low → High" in n for n in note))
		row = log_rows(self.todo.name)[-1]
		self.assertEqual(row.status, "Applied")
		self.assertEqual(json.loads(row.old_values)["values"], {"priority": "Low"})
		self.assertEqual(json.loads(row.new_values)["values"], {"priority": "High"})

	def test_a_record_changed_since_the_check_is_left_alone(self):
		change, expect = self.update({"priority": "High"}, {"priority": "Low"})
		frappe.db.set_value("ToDo", self.todo.name, "priority", "Medium")  # someone edits it

		result = self.apply(change, expect)

		self.assertTrue(result["isError"])
		self.assertIn("changed since it was checked", text(result))
		self.assertEqual(frappe.db.get_value("ToDo", self.todo.name, "priority"), "Medium")
		self.assertEqual(log_rows(self.todo.name)[-1].status, "Refused")

	def test_the_approval_covers_these_values_and_no_others(self):
		change, expect = self.update({"priority": "High"}, {"priority": "Low"})
		token = self.signed(change, expect)
		other, _expect = self.update({"priority": "Medium"}, {"priority": "Low"})

		result = self.apply(other, expect, token)

		self.assertIn("does not cover", text(result))
		self.assertEqual(frappe.db.get_value("ToDo", self.todo.name, "priority"), "Low")

	def test_an_update_needs_the_values_it_was_approved_for(self):
		change, _expect = self.update({"priority": "High"}, {"priority": "Low"})
		result = self.apply(change, None, self.signed(change, None))
		self.assertIn("needs the values the approval was given for", text(result))

	def test_a_new_record_is_created_once(self):
		change = {
			"item": "ITEM-NEW",
			"action": "create",
			"doctype": "ToDo",
			"values": {"description": "made by an approved correction", "priority": "High"},
		}
		token = self.signed(change)
		first = self.apply(change, None, token)
		second = self.apply(change, None, token)

		self.assertFalse(first["isError"], text(first))
		self.assertIn("applied already", text(second))
		self.assertEqual(frappe.db.count("ToDo", {"description": "made by an approved correction"}), 1)

	def test_table_rows_change_through_their_record(self):
		self.allow("Note")
		note = frappe.get_doc(
			{"doctype": "Note", "title": "guard rows", "seen_by": [{"user": "Administrator"}]}
		).insert(ignore_permissions=True)
		row = note.seen_by[0].name
		change = {
			"item": "ITEM-ROWS",
			"doctype": "Note",
			"name": note.name,
			"values": {},
			"rows": [{"table": "seen_by", "name": row, "values": {"user": "Guest"}}],
			"add_rows": [{"table": "seen_by", "values": {"user": "Administrator"}}],
		}
		expect = {"values": {}, "rows": {row: {"user": "Administrator"}}}

		result = self.apply(change, expect)

		self.assertFalse(result["isError"], text(result))
		note.reload()
		self.assertEqual([seen.user for seen in note.seen_by], ["Guest", "Administrator"])


class TestPairing(FrappeTestCase):
	def setUp(self):
		hold_commits(self)
		# revoking ends the hub's MCP sessions in Redis, which no rollback brings back
		sessions = patch("helpdesk_client.mcp.session.clear_sessions")
		sessions.start()
		self.addCleanup(sessions.stop)

	def test_the_site_makes_the_approval_key_and_hands_it_to_the_hub(self):
		from helpdesk_client import api

		sent = {}

		def post(url, json=None, timeout=None):
			sent.update(json)
			return MagicMock(status_code=200)

		with patch("requests.post", side_effect=post):
			api.connect_to_hub("CODE-1", hub_url="http://tbo.localhost:8002")

		self.assertTrue(sent["approval_key"])
		self.assertEqual(write_guard.approval_key(), sent["approval_key"])

		api.revoke_support_keys()
		self.assertEqual(write_guard.approval_key(), "")

	def test_the_hub_learns_this_site_checks_writes(self):
		from helpdesk_client.hub_api import capabilities_info

		self.assertIn("write_guard_v1", capabilities_info()["capabilities"])
