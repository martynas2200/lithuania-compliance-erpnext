# Lithuania Tax Compliance for ERPNext

ERPNext customization to meet Lithuanian STI (State Tax Inspectorate) requirements.

## Features

**Lithuanian Translations** — Includes comprehensive Lithuanian language translations for the ERPNext interface.

**Rounding Accounts Override** — Uses separate rounding accounts for sales and purchase documents, ensuring consistent rounding of totals.

**In Development: i.SAF Invoice Register** — Generates invoice registers by type (receivable/payable) with support for filtering, adjustment, and reporting.

<!-- **In Development: Bank Statement Import** — Note: ERPNext's built-in Plaid integration doesn't support all Lithuanian banks. Supported banks are listed [here](https://plaid.com/docs/institutions/europe/). -->

- **Item Price Dialog** —  Manage item prices directly from the Purchase Invoice form. Add, edit, or delete prices with a user-friendly dialog interface.

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app https://github.com/martynas2200/lithuania-compliance-erpnext --branch develop
bench install-app lithuania_compliance
```

If you are using this for a productive environment, it is recommended to use a custom docker image. All information about how to create and use custom images can be found in the [Frappe Docker documentation](https://github.com/frappe/frappe_docker/blob/main/docs/container-setup/02-build-setup.md).


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

MIT
