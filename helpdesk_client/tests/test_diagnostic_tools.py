# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""What the hub can learn about this site: its code, its customizations, its state, who changed what."""

import json
import subprocess
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime

import helpdesk_client.mcp.handler	# noqa: F401  (registers the tool modules)
from helpdesk_client.mcp.tools import diagnostic_tools as diag
from helpdesk_client.mcp.tools import execute_tool
from helpdesk_client.support_user import get_support_user

TRACEBACK = (
	"Traceback (most recent call last):\n"
	'  File "/home/frappe/frappe-bench/apps/frappe/frappe/app.py", line 1, in application\n'
	'  File "/home/frappe/frappe-bench/apps/helpdesk_client/helpdesk_client/probe.py", line 3, in boom\n'
	"ValueError: probe failure\n"
)


def run(tool, **arguments):
	result = execute_tool(tool, arguments)
	return result["isError"], result["content"][0]["text"]


def make_error_log(test_case, method: str, **values):
	"""An Error Log for `method`. Frappe keeps Error Logs through a rollback, so the test deletes its own."""
	test_case.addCleanup(_delete_error_logs, method)
	return frappe.get_doc({"doctype": "Error Log", "method": method, "error": TRACEBACK, **values}).insert(
		ignore_permissions=True
	)


def _delete_error_logs(method: str):
	frappe.db.delete("Error Log", {"method": method})
	frappe.db.commit()  # the rows were committed outside the test's transaction - nosemgrep


class DiagnosticCase(FrappeTestCase):
	def setUp(self):
		self.addCleanup(frappe.db.rollback)
		self.addCleanup(frappe.set_user, "Administrator")
		frappe.db.set_single_value("HDS Support Settings", "enabled", 1)


class TestCodeIdentity(DiagnosticCase):
	def test_the_app_reports_the_branch_and_commit_git_has(self):
		is_error, text = run("get_code_identity", apps=["helpdesk_client"])
		self.assertFalse(is_error, text)
		app = json.loads(text)[0]
		repo = frappe.get_app_path("helpdesk_client", "..")
		git = lambda *args: subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True).stdout.strip()	 # noqa: E731
		self.assertEqual(app["commit"], git("rev-parse", "HEAD"))
		self.assertEqual(app["branch"], git("rev-parse", "--abbrev-ref", "HEAD"))
		self.assertIn(app["dirty"], (True, False, None))
		self.assertTrue(all("@" not in (url or "").split("://")[-1].split("/")[0] for url in app["remotes"].values()))

	def test_unknown_apps_are_skipped(self):
		is_error, text = run("get_code_identity", apps=["no_such_app"])
		self.assertEqual(json.loads(text), [])

	def test_credentials_never_leave_the_site(self):
		self.assertEqual(diag.strip_credentials("https://bot:ghp_secret@github.com/org/app.git"), "https://github.com/org/app.git")
		self.assertEqual(diag.strip_credentials("git@github.com:org/app.git"), "git@github.com:org/app.git")

	def test_a_slow_git_is_not_waited_for(self):
		with patch.object(diag.subprocess, "run", side_effect=subprocess.TimeoutExpired("git", 5)):
			self.assertIsNone(diag._dirty(frappe.get_app_path("helpdesk_client", "..")))


class TestCustomizations(DiagnosticCase):
	def make_property_setter(self):
		return frappe.get_doc(
			{
				"doctype": "Property Setter",
				"doctype_or_field": "DocField",
				"doc_type": "ToDo",
				"field_name": "description",
				"property": "bold",
				"value": "1",
				"property_type": "Check",
			}
		).insert(ignore_permissions=True)

	def test_customizations_of_a_doctype(self):
		setter = self.make_property_setter()
		is_error, text = run("get_customizations", doctypes=["ToDo"])
		self.assertFalse(is_error, text)
		data = json.loads(text)
		self.assertIn(setter.name, [row["name"] for row in data["Property Setter"]])
		self.assertTrue(set(diag.CUSTOMIZATIONS) <= set(data))
		is_error, text = run("get_customizations", doctypes=["ToDo"], since=str(add_to_date(now_datetime(), days=1)))
		self.assertEqual(json.loads(text)["Property Setter"], [])

	def test_a_blocked_doctype_is_refused_in_a_list_argument(self):
		settings = frappe.get_single("HDS Support Settings")
		settings.append("blocked_doctypes", {"doctype_name": "ToDo"})
		settings.save(ignore_permissions=True)
		is_error, text = run("get_customizations", doctypes=["Note", "ToDo"])
		self.assertTrue(is_error)
		self.assertIn("blocked", text)


class TestDeployStatus(DiagnosticCase):
	def test_errors_since_are_grouped_by_signature(self):
		method = f"probe.boom_{frappe.generate_hash(length=6)}"
		make_error_log(self, method)
		make_error_log(self, method)
		is_error, text = run("get_deploy_status", since=str(add_to_date(now_datetime(), minutes=-10)))
		self.assertFalse(is_error, text)
		data = json.loads(text)
		self.assertGreaterEqual(data["errors"]["count"], 2)
		top = {row["signature"]: row["count"] for row in data["errors"]["top"]}
		self.assertEqual(top.get(f"helpdesk_client | {method} | ValueError: probe failure"), 2)
		self.assertIsInstance(data["scheduler_enabled"], bool)
		self.assertIsInstance(data["patches"], list)


class TestErrorLogFilters(DiagnosticCase):
	def test_filters_by_document_and_names_the_app(self):
		probe = frappe.generate_hash(length=6)
		make_error_log(self, f"probe.ref_{probe}", reference_doctype="ToDo", reference_name=f"mcp-{probe}")
		make_error_log(self, f"probe.other_{probe}")
		is_error, text = run("get_error_log", reference_doctype="ToDo", reference_name=f"mcp-{probe}")
		self.assertFalse(is_error, text)
		rows = json.loads(text)
		self.assertEqual([r["reference_name"] for r in rows], [f"mcp-{probe}"])
		self.assertEqual(rows[0]["app"], "helpdesk_client")
		self.assertEqual(rows[0]["top_frames"][-1].split(",")[0], 'helpdesk_client/helpdesk_client/probe.py"')


class TestVersionHistory(DiagnosticCase):
	def test_who_changed_the_record_and_what(self):
		# Support Ticket keeps its change history (track_changes); ToDo does not
		ticket = frappe.get_doc(
			{"doctype": "Support Ticket", "subject": "Version probe", "description": "<p>probe</p>"}
		).insert(ignore_permissions=True)
		ticket.priority = "High"
		# tests skip version tracking unless a save asks for it
		ticket.save(ignore_permissions=True, ignore_version=False)
		support_user = get_support_user()
		if frappe.db.exists("User", support_user):
			frappe.set_user(support_user)
			ticket.reload()
			ticket.priority = "Urgent"
			ticket.save(ignore_permissions=True, ignore_version=False)
			frappe.set_user("Administrator")
		is_error, text = run("get_version_history", doctype="Support Ticket", name=ticket.name)
		self.assertFalse(is_error, text)
		history = json.loads(text)["history"]
		actors = [h["actor"] for h in history]
		self.assertIn("system", actors)
		if frappe.db.exists("User", support_user):
			self.assertEqual(history[0]["actor"], "hub")
		self.assertIn("priority", [c["field"] for h in history for c in h["changed"]])

	def test_actor_rules(self):
		self.assertEqual(diag.actor_of(get_support_user()), "hub")
		self.assertEqual(diag.actor_of("Administrator"), "system")
		self.assertEqual(diag.actor_of("someone@example.com"), "person")
		self.assertEqual(diag.actor_of("someone@example.com", data_import="DI-0001"), "import")
