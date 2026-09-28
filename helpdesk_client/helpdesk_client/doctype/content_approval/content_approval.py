# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification
from frappe.model.document import Document
from frappe.utils import now_datetime

APPROVER_ROLE = "Content Approver"


class ContentApproval(Document):
	def validate(self):
		self.validate_comment_for_changes()
		self.set_decision_meta()

	def after_insert(self):
		self.notify_approvers()

	def validate_comment_for_changes(self):
		if self.status == "Changes Requested" and not (self.client_comment or "").strip():
			frappe.throw(_("Tell the team what to change before requesting changes"))

	def set_decision_meta(self):
		if self.status == "Pending":
			# re-sent after changes: the previous decision no longer applies
			self.decided_by = None
			self.decided_on = None
		elif self.has_value_changed("status"):
			self.decided_by = frappe.session.user
			self.decided_on = now_datetime()

	def notify_approvers(self):
		approvers = self.get_approvers()
		if not approvers:
			return
		enqueue_create_notification(
			approvers,
			{
				"type": "Alert",
				"document_type": self.doctype,
				"document_name": self.name,
				"subject": _("New content to approve: {0} ({1})").format(frappe.bold(self.title), self.channel),
				"from_user": frappe.session.user,
			},
		)

	@staticmethod
	def get_approvers() -> list[str]:
		"""Users with the approver role; System Managers if nobody has it yet."""
		for role in (APPROVER_ROLE, "System Manager"):
			users = frappe.get_all(
				"Has Role",
				filters={"role": role, "parenttype": "User", "parent": ("not in", ["Administrator", "Guest"])},
				pluck="parent",
			)
			users = [u for u in set(users) if frappe.db.get_value("User", u, "enabled")]
			if users:
				return users
		return []
