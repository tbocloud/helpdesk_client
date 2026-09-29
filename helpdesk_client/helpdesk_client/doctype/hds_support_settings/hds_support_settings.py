# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

from helpdesk_client.utils import normalize_site_url
from helpdesk_client.utils.session_replay import MAX_MINUTES, MIN_MINUTES


class HDSSupportSettings(Document):
	# validate() checks local values only. The previous validate_sp_access()
	# called the Helpdesk on every save using a stored API token — the exact
	# exposure this redesign removes. The client holds no credentials and
	# makes no outbound calls, so nothing is ever validated remotely.
	def validate(self):
		self.validate_replay_minutes()

	def before_save(self):
		if self.qcs_hub_url:
			self.qcs_hub_url = normalize_site_url(self.qcs_hub_url)

	def validate_replay_minutes(self):
		if not self.enable_session_replay:
			return
		if not MIN_MINUTES <= cint(self.replay_minutes) <= MAX_MINUTES:
			frappe.throw(
				_("Replay Minutes must be between {0} and {1}.").format(MIN_MINUTES, MAX_MINUTES),
				title=_("Session Replay"),
			)
