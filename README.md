### Helpdesk Client

helpdesk_client

### What TBO Support (the hub) can read here

The hub reaches this site over MCP (`helpdesk_client.mcp.handler.handle`) with the support user's API key, checked on every request. Its read tools obey **HDS Support Settings** (enabled, allowed and blocked doctypes, limits); writes also need **Allow Write Operations**. Besides `get_doc`, `get_list`, `get_count`, `get_meta`, `execute_report`, `get_error_log` (filters by time, method and document; each row names the app it came from and its top frames), `get_installed_apps` and `get_site_info`, the diagnostic tools are:

- `get_code_identity`: per app the version, branch, commit, remotes (credentials removed) and uncommitted changes.
- `get_customizations`: custom fields, property setters, client and server scripts, workflows, print formats and notifications, optionally for some doctypes or since a date.
- `get_deploy_status`: patches run, scheduler, workers, and the errors since a time grouped by signature.
- `get_version_history`: who changed a record and what, each change marked hub, system, import or person.

Every argument that names a doctype, including lists, is checked against the allowed and blocked lists.

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
