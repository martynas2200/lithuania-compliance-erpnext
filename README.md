# Lithuania Tax Compliance for ERPNext

ERPNext customization to facilitate meeting Lithuanian STI (State Tax Inspectorate) requirements.

## Features

- **Lithuanian Translations** — Includes comprehensive Lithuanian language translations for the ERPNext interface.

- **Rounding Accounts Override** — Uses separate rounding accounts for sales and purchase documents/.

- **Bank Statement Import** — Note: ERPNext's built-in Plaid integration doesn't support all Lithuanian banks. Supported banks are listed [here](https://plaid.com/docs/institutions/europe/).

- **Item Price Dialog** —  Manage item prices directly from the Purchase Invoice form. Add, edit, or delete prices with a user-friendly dialog interface.

- **Buying Price Check** — On Purchase Invoice submission, compares each item's invoice rate with its current buying price. If the invoice rate is higher, a dialog shows a comparison table and lets you select which items to record a new buying price for.

- **i.SAF Invoice Register** — Generates invoice registers by type of receivable or payable.

- **Automatic Supplier Linking** — For each submitted Purchase Invoice, it enqueues a background job that adds the invoice supplier to the supplier list of every item on the invoice.


- **VAT Invoice Type Classification** — Categorises invoices for i.SAF compliance:

  - Sales Invoices:
    - Exclude from i.SAF
    - Issued SF: Standard VAT invoice
    - Received DS: Debit VAT invoice
    - Issued KS: Credit VAT invoice
    - Issued VS: Summary VAT invoice
    - Received VD: Summary debit VAT invoice
    - Issued VK: Summary credit VAT invoice

  - Purchase Invoices:
    - Exclude from i.SAF
    - Received SF: Standard VAT invoice
    - Issued DS: Debit VAT invoice
    - Received KS: Credit VAT invoice
    - Received VS: Summary VAT invoice
    - Issued VD: Summary debit VAT invoice
    - Received VK: Summary credit VAT invoice

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app https://github.com/martynas2200/lithuania-compliance-erpnext --branch develop
bench install-app lithuania_compliance
```

If you are using this for a productive environment, it is recommended to use a custom docker image. All information about how to create and use custom images can be found in the [Frappe Docker documentation](https://github.com/frappe/frappe_docker).


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
