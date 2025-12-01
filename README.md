# Lithuania Tax Compliance for ERPNext

ERPNext customization to meet Lithuanian STI (State Tax Inspectorate) requirements.

## Features

**Rounding Accounts Override** — Uses separate rounding accounts for sales and purchase documents, ensuring consistent rounding of totals.

**In Development: i.SAF Invoice Register** — Generates invoices registers by type (receivable/payable) with support for filtering, adjustment, and reporting.

**In Development: Bank Statement Import** — Note: ERPNext's built-in Plaid integration doesn't support all Lithuanian banks. Supported banks are listed [here](https://plaid.com/docs/institutions/europe/).

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app https://github.com/martynas2200/lithuania-compliance-erpnext --branch develop
bench install-app lithuania_compliance
```

If you are using for a productive environment, it is recommended to use a custom docker image. All information about how to create and use custom images can be found in the [Frappe Docker documentation](https://github.com/frappe/frappe_docker/blob/main/docs/container-setup/02-build-setup.md).


### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:
```bash
cd apps/lithuania_compliance
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:
- ruff
- eslint
- prettier
- pyupgrade

### License

mit
