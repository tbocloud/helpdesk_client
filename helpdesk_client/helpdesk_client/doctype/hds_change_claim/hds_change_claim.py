# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""The one right to apply an approved change item on this site.

Written only by the connector (helpdesk_client.mcp.write_guard.claim), in the same
transaction as the write it guards: the row's name is the change set and item, so a
second, simultaneous apply of the same item cannot insert it and is refused. A write
that fails rolls its claim back with it, so the item can still be applied.
"""

from frappe.model.document import Document


class HDSChangeClaim(Document):
	pass
