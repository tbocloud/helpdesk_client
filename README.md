### Helpdesk Client

helpdesk_client

### What TBO Support (the hub) can read here

The hub reaches this site over MCP (`helpdesk_client.mcp.handler.handle`) with the support user's API key, checked on every request. Its read tools obey **HDS Support Settings** (enabled, allowed and blocked doctypes, limits); writes also need **Allow Write Operations**. Besides `get_doc`, `get_list`, `get_count`, `get_meta`, `execute_report`, `get_error_log` (filters by time, method and document; each row names the app it came from and its top frames), `get_installed_apps` and `get_site_info`, the diagnostic tools are:

- `get_code_identity`: per app the version, branch, commit, remotes (credentials removed) and uncommitted changes.
- `get_customizations`: custom fields, property setters, client and server scripts, workflows, print formats and notifications, optionally for some doctypes or since a date.
- `get_deploy_status`: patches run, scheduler, workers, and the errors since a time grouped by signature.
- `get_version_history`: who changed a record and what, each change marked hub, system, import or person.

Every argument that names a doctype, including lists, is checked against the allowed and blocked lists.

### What TBO Support (the hub) may change here

Every write from the hub passes this site's guard (`helpdesk_client.mcp.write_guard`), whatever the hub asks:

1. support enabled, and **Allow Write Operations** on;
2. the doctype not blocked (and in the allowed list when there is one); a table row is judged by the record it belongs to;
3. never users, roles and permissions, system and email settings, OAuth and connected apps, scripts and scheduled jobs, custom fields, property setters, doctypes, workflows, print formats, bulk updates and data imports, or this app's own settings and log;
4. the doctype on the **Write List** (HDS Support Settings) with that action: update, create, or submit and cancel. Nothing is deleted;
5. on a **Production** site (the default), an approval the hub signed with this site's **Approval Key** for exactly that record and those values, and not expired.

The approval key is made by this site when its System Manager connects it to TBO Support (`connect_to_hub`), handed to the hub, and forgotten when the pairing ends. A site paired before this version connects once more to get one. The write list starts empty: a site takes no write from TBO Support until its System Manager fills it.

Corrections use two tools. `check_change` writes nothing and runs none of this site's code: it returns the guard's verdict, any field or value problems, and the record's current values. `apply_change` changes one record: it leaves the record alone when a field it changes no longer holds the approved old value, saves with the site's normal validation, and adds a note to the record's timeline. Every write, applied, refused or failed, is a row in **HDS Change Log** (who approved it, the change set, the old and new values), which this site's System Managers can read.

### Who may raise a ticket here

The Support button (the chat, or the form) is for the customer's own users. TBO Support signed in here as its support user (**Login to site** on the hub) gets a notice instead, and `chat.start`, `chat.send` and `create_ticket` refuse it, so a ticket never names TBO as the customer. Administrator still raises tickets as the site's **Fallback Contact Email**.

### The Support panel: one chat per ticket

With the chat on, the round Support button opens the **Support panel** (`public/js/chat_panel.js`). It has three tabs:

- **Tickets:** a dropdown of the user's tickets. Each shows a dot, the ticket's name and a one-line summary, and opens that ticket's own chat.
- **New chat:** chats that did not become tickets.
- **Action needed:** the red tickets, each with what is needed. Picking one opens its chat.

**Full page** opens the same at `/app/support-chat`, and `/app/support-chat/SUP-…` opens one ticket's chat. The panel and the page share the chat view in `public/js/chat_view.js`; the server side is `inbox.py`.

- **The dots** (`inbox.state`):
  - 🟢 the user confirmed the fix, or the ticket is closed;
  - 🔴 TBO Support waits for the user: a fix to check (Resolved), or an answer (Replied, Waiting on Customer, or the stage Waiting for you);
  - 🟠 the team is working on it.

  A confirm or reopen counts only until TBO Support changes the ticket's status again (`last_synced`), so a ticket fixed a second time asks again.
- **A red button** above the Support button shows **Actions needed · n** while tickets wait for the user. Its count comes from boot and is refreshed live.
- **A new chat** first asks "Is this a new problem, or about one of your open tickets?" and lists them.
- **A ticket raised with the form** gets its chat the first time it is opened (`chat.open_ticket`). Its text and TBO Support's updates come first, then TBO Support links a chat to the ticket (hub action `open_ticket`). Before TBO Support has picked the ticket up, or with an older hub, its story shows read-only.
- **What's the status?** is answered on this site from the ticket (stage, latest update, who has it, what is needed); nobody at TBO Support is asked.
- **Only the user closes a ticket.** In a ticket's chat, **It's fixed**, **Still broken** and **It came back** (on a closed ticket) set the ticket's own confirmation, as its form does. TBO Support applies it once on its next sync (every 5 minutes). A closed ticket's chat takes no more messages.
- **Notices and reminders:**
  - When a ticket turns red, the user gets one notice saying what is needed, linked to its chat.
  - A fix waiting for the user's check is brought up again every 3 days until they answer (`inbox.remind_unconfirmed`, daily).

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app helpdesk_client
```

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/helpdesk_client
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### CI

This app can use GitHub Actions for CI. The following workflows are configured:

- CI: Installs this app and runs unit tests on every push to `develop` branch.
- Linters: Runs [Frappe Semgrep Rules](https://github.com/frappe/semgrep-rules) and [pip-audit](https://pypi.org/project/pip-audit/) on every pull request.


### License

mit
# helpdesk_client
