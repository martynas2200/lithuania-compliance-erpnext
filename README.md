### Lithuanian Tax Compliance for ERPNext

Adjust ERPNext to adhere to STI requirements.

### Features

#### Rounding accounts override

This app overrides the usual method for rounding accounts to comply with Lithuanian rounding rules and STI requirements.
It ensures sales and purchase documents uses different rounding accounts so that totals, VAT, and residuals are rounded consistently across sales and purchase documents.

#### i.SAF invoice register

The program can generate a register of i.SAF invoices by types:

- Invoices receivable;
- Invoices payable.

Invoices are selected for the register according to the filters. The generated report can be viewed, and if necessary, the amount and VAT can be adjusted.


#### In Progress: Additional Bank Statement Import
ERPNext have a built-in bank statement import functionality using Plaid integration. However, Plaid does not support all banks in Lithuania. Supported banks of Plaid can be found [here](https://plaid.com/docs/institutions/europe/).

<!-- This app adds an ability to import bank statements from Swedbank using their provided XML format. -->

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app lithuanian_compliance
```

If you are using for a productive environment, it is recommended to use a custom docker image. All information about how to create and use custom images can be found in the [Frappe Docker documentation](https://github.com/frappe/frappe_docker/blob/main/docs/container-setup/02-build-setup.md).


### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:
```bash
cd apps/lithuanian_compliance
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:
- ruff
- eslint
- prettier
- pyupgrade

### License

mit
