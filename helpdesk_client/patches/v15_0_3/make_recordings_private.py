# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Recordings and screenshots attached to tickets become private files.

Sites that never set Save Recording uploaded them as public files, readable
by anyone with the link. The work is helpdesk_client.setup.make_recordings_private:
a file that could not be moved is logged and tried again on every later
migrate (after_migrate), and never stops the customer's migrate.
"""

from helpdesk_client.setup import make_recordings_private


def execute():
	make_recordings_private()
