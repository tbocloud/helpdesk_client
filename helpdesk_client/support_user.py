"""Who the TBO Support hub signs in as on this site, and the hub it talks to.

Stored in HDS Support Settings. Sites registered before this was configurable
keep the old support@quarkcs.com user, so their hub connection keeps working.
"""

import frappe

DEFAULT_SUPPORT_USER = "support@teambackoffice.com"
LEGACY_SUPPORT_USER = "support@quarkcs.com"
DEFAULT_HUB_URL = "https://teams.teambackoffice.com"
LEGACY_HUB_URL = "https://support.quarkcs.com"


def get_support_user() -> str:
	configured = frappe.db.get_value(  # get_single_value throws until migrate adds the field - nosemgrep
		"HDS Support Settings", None, "support_user"
	)
	if configured:
		return configured
	if frappe.db.exists("User", LEGACY_SUPPORT_USER):
		return LEGACY_SUPPORT_USER
	return DEFAULT_SUPPORT_USER
