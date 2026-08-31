"""CAMT bank statement import.

Tested with Swedbank ISO_XML_052 (CAMT052)
"""
# TODO: find_existing_document is quite broad, as we make payments between our own accounts, we want a single entry, but what if we have the same date and same amount multiple times... use transaction_id or something...

from __future__ import annotations

import datetime
import hashlib
import re
from dataclasses import dataclass, field
from typing import Literal

import frappe
from bs4 import BeautifulSoup
from erpnext.setup.utils import get_exchange_rate
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt
from frappe.utils.data import get_url_to_form


class BankImporter(Document):
	pass


@dataclass
class AccountContext:
	account: str
	company: str
	bank_account: str | None


@dataclass
class PartyDetails:
	name: str = ""
	iban: str = ""
	address: str = ""


@dataclass
class CamtTransaction:
	date: str
	direction: Literal["CRDT", "DBIT"]
	amount: float
	currency: str
	reference_no: str
	remittance_reference: str
	structured_reference: str | None
	party_name: str
	party_iban: str
	party_address: str
	subfamily_code: str
	charges: float = 0.0


@dataclass
class MatchResult:
	party_type: str | None = None
	party: str | None = None
	employee: str | None = None
	invoice_references: list[str] = field(default_factory=list)
	expense_references: list[str] = field(default_factory=list)


@dataclass
class PostingPlan:
	# Empty payment_type is allowed for a placeholder/unplanned plan (e.g. in
	# preview when a posting plan cannot be built).
	payment_type: Literal["Receive", "Pay", "Internal Transfer", "CDPT", ""] = ""
	paid_from: str | None = None
	paid_to: str | None = None
	party_type: str | None = None
	party: str | None = None
	references: list[str] = field(default_factory=list)
	cost_center: str | None = None


@dataclass
class ImportResult:
	document_name: str | None = None
	document_type: str | None = None
	submitted: bool = False
	party_type: str | None = None
	party: str | None = None
	error: str | None = None


def get_settings():
	return frappe.get_cached_doc("Lithuania Compliance Settings", "Lithuania Compliance Settings")


@frappe.whitelist()
def read_camt054(content, account=None, auto_submit=False):
	"""Import a CAMT.052/.053/.054 file and return created accounting records."""
	settings = get_settings()
	context = resolve_account_context(content, account)
	auto_submit = as_bool(auto_submit)
	results = [
		import_transaction(transaction, context, settings, auto_submit)
		for transaction in parse_camt_transactions(content, settings)
	]
	return build_import_summary(results, context.company)


@frappe.whitelist()
def import_camt_statement(content, auto_submit=False):
	"""Page-friendly wrapper that returns errors instead of raising them."""
	try:
		result = read_camt054(content, auto_submit=auto_submit)
		return {"summary": result["message"], "records": result["records"], "errors": []}
	except Exception as error:
		frappe.log_error("LT Bank Statement Import", frappe.get_traceback())
		return {"summary": _("Import failed: {0}").format(error), "records": [], "errors": [str(error)]}


@frappe.whitelist()
def preview_camt(content, account=None):
	"""Parse a CAMT file and return transaction previews without creating any documents."""
	settings = get_settings()
	context = resolve_account_context(content, account)
	transactions = parse_camt_transactions(content, settings)

	preview_data = []
	for txn in transactions:
		try:
			matches = find_matches(txn, settings)
			party_type, party = resolve_party_from_iban(txn, context.company)
			plan = build_posting_plan(txn, matches, party_type, party, context, settings)
		except Exception:
			party_type = None
			party = None
			plan = PostingPlan()

		direction_label = _("Incoming") if txn.direction == "CRDT" else _("Outgoing")
		action_label = {
			"Receive": _("Receive payment"),
			"Pay": _("Make payment"),
			"Internal Transfer": _("Internal transfer"),
			"CDPT": _("Cash deposit"),
		}.get(plan.payment_type, plan.payment_type or _("Unknown"))

		preview_data.append(
			{
				"date": txn.date,
				"direction": txn.direction,
				"direction_label": direction_label,
				"amount": txn.amount,
				"currency": txn.currency,
				"party_name": txn.party_name or "",
				"party_iban": txn.party_iban or "",
				"remittance_reference": txn.remittance_reference or "",
				"subfamily_code": txn.subfamily_code or "",
				"charges": txn.charges,
				"action": action_label,
				"payment_type": plan.payment_type or "",
				"matched_party_type": plan.party_type or "",
				"matched_party": plan.party or "",
				"paid_from": plan.paid_from or "",
				"paid_to": plan.paid_to or "",
				"reference_count": len(plan.references),
			}
		)

	total_credit = sum(t.amount for t in transactions if t.direction == "CRDT")
	total_debit = sum(t.amount for t in transactions if t.direction == "DBIT")

	return {
		"company": context.company,
		"bank_account": context.bank_account,
		"account": context.account,
		"total_transactions": len(preview_data),
		"total_credit": total_credit,
		"total_debit": total_debit,
		"transactions": preview_data,
	}


def as_bool(value) -> bool:
	return str(value).lower() in {"1", "true", "yes"}


def resolve_account_context(content, account) -> AccountContext:
	account = account or get_company_account_by_iban(extract_statement_iban(content))
	if not account:
		frappe.throw(_("Bank account not found for IBAN in CAMT file"))

	company = frappe.get_value("Account", account, "company")
	bank_account = frappe.db.get_value(
		"Bank Account",
		{"account": account, "is_company_account": 1, "disabled": 0},
		"name",
	)
	return AccountContext(account=account, company=company, bank_account=bank_account)


def extract_statement_iban(content) -> str:
	soup = BeautifulSoup(content, "lxml")
	for path in (
		("bktocstmracctrpt", "rpt"),
		("bktocstmrstmt", "stmt"),
	):
		report = getattr(getattr(soup.document, path[0], None), path[1], None)
		iban = getattr(getattr(getattr(report, "acct", None), "id", None), "iban", None)
		if iban:
			return iban.get_text(strip=True)
	frappe.throw(_("IBAN not found in CAMT file"))


def parse_camt_transactions(content, settings=None) -> list[CamtTransaction]:
	soup = BeautifulSoup(content, "lxml")
	return [transaction for entry in soup.find_all("ntry") for transaction in parse_entry(entry, settings)]


def parse_entry(entry, settings=None) -> list[CamtTransaction]:
	entry_soup = BeautifulSoup(str(entry), "lxml")
	transactions = entry_soup.find_all("txdtls")
	if not transactions:
		return []

	entry_amount, entry_currency = extract_amount(entry_soup)
	date = extract_booking_date(entry_soup)
	global_reference = get_text(entry_soup, "acctsvcrref")
	subfamily_code = extract_subfamily_code(entry_soup)
	return [
		parse_transaction(
			entry_soup,
			transaction,
			date,
			entry_amount,
			entry_currency,
			global_reference,
			subfamily_code,
			index,
			bool(settings and cint(getattr(settings, "always_use_entry_transaction_type", 0))),
		)
		for index, transaction in enumerate(transactions, start=1)
	]


# TODO: introduce always_use_entry_transaction_type


def parse_transaction(
	entry,
	transaction,
	date,
	entry_amount,
	entry_currency,
	global_reference,
	subfamily_code,
	index,
	use_entry_direction,
):
	transaction_soup = BeautifulSoup(str(transaction), "lxml")
	direction = (
		get_text(entry, "cdtdbtind") if use_entry_direction else get_text(transaction_soup, "cdtdbtind")
	)
	direction = direction or get_text(entry, "cdtdbtind")
	amount, currency = extract_amount(transaction_soup, entry_amount, entry_currency)
	party = extract_party(transaction_soup, direction)
	reference_no = extract_reference(
		entry, transaction_soup, date, amount, party.name, global_reference, index
	)
	structured_reference = get_nested_text(transaction_soup, "rmtinf", "strd", "cdtrrefinf", "ref")
	remittance_reference = (
		structured_reference
		or get_nested_text(transaction_soup, "rmtinf", "ustrd")
		or get_text(transaction_soup, "endtoendid")
		or get_text(transaction_soup, "addtltxinf")
		or reference_no
	)
	return CamtTransaction(
		date=date,
		direction=direction,
		amount=amount,
		currency=currency,
		reference_no=reference_no,
		remittance_reference=remittance_reference,
		structured_reference=structured_reference,
		party_name=party.name,
		party_iban=party.iban,
		party_address=party.address,
		subfamily_code=subfamily_code,
		charges=extract_charges(transaction_soup),
	)


def extract_booking_date(entry) -> str:
	date = get_nested_text(entry, "bookgdt", "dt") or get_nested_text(entry, "bookgdt", "dttm")
	return date[:10] if date else datetime.date.today().isoformat()


def extract_amount(soup, fallback_amount=None, fallback_currency=None) -> tuple[float, str]:
	amount_tag = get_nested_tag(soup, "txamt", "amt") or soup.find("amt")
	if amount_tag:
		return flt(amount_tag.get_text()), amount_tag.get("ccy") or fallback_currency or ""
	return fallback_amount or 0.0, fallback_currency or ""


def extract_reference(entry, transaction, date, amount, party_name, global_reference, index) -> str:
	candidates = (
		get_nested_text(transaction, "refs", "uetr"),
		get_nested_text(transaction, "refs", "acctsvcrref"),
		get_text(transaction, "txid"),
		get_text(transaction, "pmtinfid"),
		get_text(entry, "ntryref"),
		f"{global_reference}-{index}" if global_reference else None,
		get_nested_text(entry, "bktxcd", "prtry", "cd"),
	)
	for reference in candidates:
		if reference:
			return reference
	return hashlib.md5(f"{date}:{amount}:{party_name}".encode()).hexdigest()


def extract_subfamily_code(entry) -> str:
	return get_nested_text(entry, "bktxcd", "domn", "fmly", "subfmlycd").upper()


def extract_charges(transaction) -> float:
	charges = get_nested_text(transaction, "chrgs", "ttlchrgsandtaxamt", "amt") or get_nested_text(
		transaction, "chrgs", "amt"
	)
	return flt(charges) if charges else 0.0


def extract_party(transaction, direction) -> PartyDetails:
	party_tag = get_nested_tag(transaction, "txdtls", "rltdpties", "cdtr" if direction == "DBIT" else "dbtr")
	iban_tag = get_nested_tag(transaction, "cdtracct" if direction == "DBIT" else "dbtracct", "id", "iban")
	if not party_tag:
		return PartyDetails(iban=get_text(iban_tag))

	party_soup = BeautifulSoup(str(party_tag), "lxml")
	name = get_text(party_soup, "nm") or get_first_address_line(party_soup)
	address = format_party_address(party_soup)
	return PartyDetails(name=name, iban=get_text(iban_tag), address=address)


def get_first_address_line(soup) -> str:
	lines = soup.find_all("adrline")
	return lines[0].get_text(strip=True) if lines else ""


def format_party_address(soup) -> str:
	street = get_text(soup, "strtnm")
	if street:
		line_one = " ".join(filter(None, (street, get_text(soup, "bldgnb"))))
		line_two = " ".join(filter(None, (get_text(soup, "pstcd"), get_text(soup, "twnnm"))))
	else:
		lines = [line.get_text(strip=True) for line in soup.find_all("adrline")]
		line_one, line_two = ([*lines, "", ""])[:2]
	return ", ".join(filter(None, (line_one, line_two, get_text(soup, "ctry"))))


def get_nested_tag(soup, *names):
	current = soup
	for name in names:
		current = getattr(current, name, None)
		if not current:
			return None
	return current


def get_nested_text(soup, *names) -> str:
	return get_text(get_nested_tag(soup, *names))


def get_text(tag, name=None) -> str:
	tag = getattr(tag, name, None) if name else tag
	return tag.get_text(strip=True) if tag else ""


def import_transaction(txn, context, settings, auto_submit) -> ImportResult:
	bank_transaction = None
	try:
		matches = find_matches(txn, settings)
		party_type, party = resolve_party_from_iban(txn, context.company)
		plan = None
		plan_error = None
		try:
			plan = build_posting_plan(txn, matches, party_type, party, context, settings)
			validate_posting_plan(plan)
		except Exception as error:
			plan_error = error
			frappe.log_error("Bank Import Posting Plan Error", frappe.get_traceback())

		# Create the Bank Transaction once, even if the plan is invalid.
		bank_transaction = get_or_create_bank_transaction(txn, plan, context, settings)
		frappe.db.commit()

		if plan_error and bank_transaction:
			return ImportResult(bank_transaction.name, "Bank Transaction", error=str(plan_error))
		elif plan_error:
			return ImportResult(error=str(plan_error))

		enrich_bank_transaction(bank_transaction, plan, txn)

		existing = find_existing_document(txn, plan, context.company)
		if existing:
			link_bank_transaction(bank_transaction, existing[0], existing[1], txn.amount)
			frappe.db.commit()
			return ImportResult(existing[1], existing[0], party_type=plan.party_type, party=plan.party)

		if plan.payment_type == "CDPT":
			name, submitted = create_cash_deposit_entry(txn, plan, context, auto_submit)
			document_type = "Journal Entry"
		else:
			result = create_payment_entry_from_plan(txn, plan, context, auto_submit)
			name, submitted, document_type = result["payment_entry"], result["submitted"], "Payment Entry"
		link_bank_transaction(bank_transaction, document_type, name, txn.amount)
		create_fee_entry(txn, context, settings, bank_transaction, auto_submit)
		frappe.db.commit()
		return ImportResult(name, document_type, submitted, plan.party_type, plan.party)
	except Exception as error:
		frappe.log_error("Bank Import CAMT", frappe.get_traceback())
		if bank_transaction:
			frappe.db.commit()
			return ImportResult(bank_transaction.name, "Bank Transaction", error=str(error))
		return ImportResult(error=str(error))


def find_matches(txn, settings) -> MatchResult:
	if txn.direction == "DBIT":
		return MatchResult(
			party=find_supplier(txn.party_name), party_type="Supplier", employee=get_employee(txn.party_name)
		)

	customer = frappe.db.get_value("Customer", {"customer_name": txn.party_name, "disabled": 0}, "name")
	invoices = find_matching_sales_invoices(txn.remittance_reference, settings)
	return MatchResult(party_type="Customer", party=customer, invoice_references=invoices)


def find_matching_sales_invoices(reference, settings) -> list[str]:
	invoices = frappe.get_all(
		"Sales Invoice",
		filters=[["outstanding_amount", ">", 0], ["docstatus", "=", 1]],
		fields=["name"],
	)
	return [invoice.name for invoice in invoices if reference_matches(invoice.name, reference, settings)]


def reference_matches(invoice_name, reference, settings) -> bool:
	if invoice_name in reference:
		return True
	if cint(settings.numeric_only_debtor_matching):
		return numeric_reference(invoice_name) in reference
	if cint(settings.ignore_special_characters):
		return normalize_reference(invoice_name) in normalize_reference(reference)
	return False


def resolve_party_from_iban(txn, company) -> tuple[str | None, str | None]:
	if not (txn.party_iban or txn.party_name):
		return None, None
	try:
		return get_or_create_party_from_iban(txn.party_name, txn.party_iban, txn.direction == "CRDT", company)
	except Exception:
		frappe.log_error("Bank Import: party lookup", frappe.get_traceback())
		return None, None


def build_posting_plan(txn, matches, iban_party_type, iban_party, context, settings) -> PostingPlan:
	mapped_account = get_account_by_structured_reference(txn.structured_reference, settings)
	if txn.direction == "CRDT":
		return build_incoming_plan(
			txn, matches, iban_party_type, iban_party, mapped_account, context, settings
		)
	return build_outgoing_plan(txn, matches, iban_party_type, iban_party, mapped_account, context, settings)


def build_incoming_plan(
	txn, matches, iban_party_type, iban_party, mapped_account, context, settings
) -> PostingPlan:
	if mapped_account:
		return PostingPlan("Internal Transfer", paid_from=mapped_account, paid_to=context.account)
	if txn.subfamily_code == "CDPT" and settings.cash_deposit_account and settings.cash_deposit_employee:
		return PostingPlan(
			"CDPT", settings.cash_deposit_account, context.account, "Employee", settings.cash_deposit_employee
		)
	if txn.subfamily_code == "POSP" and settings.emv_account:
		return PostingPlan("Internal Transfer", settings.emv_account, context.account)
	internal_account = get_internal_transfer_account(txn.party_iban, context)
	if txn.subfamily_code == "BOOK" and internal_account:
		return PostingPlan("Internal Transfer", internal_account, context.account)
	if matches.invoice_references:
		customer = frappe.get_value("Sales Invoice", matches.invoice_references[0], "customer")
		return PostingPlan(
			"Receive",
			paid_to=context.account,
			party_type="Customer",
			party=customer,
			references=matches.invoice_references,
		)
	if iban_party_type and iban_party:
		return PostingPlan("Receive", paid_to=context.account, party_type=iban_party_type, party=iban_party)
	if matches.party:
		return PostingPlan("Receive", paid_to=context.account, party_type="Customer", party=matches.party)
	if settings.cash_deposit_account:
		return PostingPlan("Internal Transfer", context.account, settings.cash_deposit_account)
	return PostingPlan(
		"Receive", paid_to=context.account, party_type="Customer", party=settings.default_customer
	)


def build_outgoing_plan(
	txn, matches, iban_party_type, iban_party, mapped_account, context, settings
) -> PostingPlan:
	if mapped_account:
		return PostingPlan("Internal Transfer", context.account, mapped_account)
	if txn.subfamily_code == "CHRG" and settings.bank_fee_expense_account:
		return PostingPlan(
			"Internal Transfer",
			context.account,
			settings.bank_fee_expense_account,
			cost_center=settings.bank_fee_cost_center,
		)
	internal_account = get_internal_transfer_account(txn.party_iban, context)
	if txn.subfamily_code == "BOOK" and internal_account:
		return PostingPlan("Internal Transfer", context.account, internal_account)
	if matches.employee and matches.expense_references:
		return PostingPlan(
			"Pay",
			context.account,
			party_type="Employee",
			party=matches.employee,
			references=matches.expense_references,
		)
	if matches.employee:
		return PostingPlan("Pay", context.account, party_type="Employee", party=matches.employee)
	if iban_party_type and iban_party:
		return PostingPlan("Pay", context.account, party_type=iban_party_type, party=iban_party)
	if matches.party:
		return PostingPlan("Pay", context.account, party_type="Supplier", party=matches.party)
	frappe.throw(
		_("Could not determine a party or destination account for outgoing transaction {0}").format(
			txn.reference_no
		)
	)


def get_internal_transfer_account(iban, context) -> str | None:
	account = get_company_account_by_iban(iban) if iban else None
	if not account or account == context.account:
		return None
	return account if frappe.get_value("Account", account, "company") == context.company else None


def validate_posting_plan(plan):
	if plan.payment_type == "Receive" and not plan.paid_to:
		frappe.throw(_("Missing receiving account"))
	if plan.payment_type == "Pay" and not plan.paid_from:
		frappe.throw(_("Missing paying account"))
	if plan.payment_type in {"Internal Transfer", "CDPT"} and not (plan.paid_from and plan.paid_to):
		frappe.throw(_("Missing account for internal transfer"))


def find_existing_document(txn, plan, company) -> tuple[str, str] | None:
	if plan.payment_type == "CDPT" and txn.reference_no:
		name = frappe.db.get_value(
			"Journal Entry", {"cheque_no": txn.reference_no, "company": company}, "name"
		)
		return ("Journal Entry", name) if name else None
	if plan.payment_type == "Internal Transfer":
		name = frappe.db.get_value(
			"Payment Entry",
			{
				"payment_type": "Internal Transfer",
				"paid_from": plan.paid_from,
				"paid_to": plan.paid_to,
				"paid_amount": txn.amount,
				"posting_date": txn.date,
			},
			"name",
		)
	else:
		name = frappe.db.get_value(
			"Payment Entry", {"reference_no": txn.reference_no, "company": company}, "name"
		)
	return ("Payment Entry", name) if name else None


def get_or_create_bank_transaction(txn, plan, context, settings):
	if not context.bank_account:
		return None
	name = frappe.db.get_value(
		"Bank Transaction", {"bank_account": context.bank_account, "transaction_id": txn.reference_no}, "name"
	)
	if name:
		return frappe.get_doc("Bank Transaction", name)

	amount = txn.amount + txn.charges if should_split_fee(txn, settings) else txn.amount
	document = frappe.get_doc(
		{
			"doctype": "Bank Transaction",
			"bank_account": context.bank_account,
			"date": txn.date,
			"currency": txn.currency,
			"description": (
				get_full_remarks(plan, txn) if plan else (txn.remittance_reference or txn.reference_no)
			),
			"reference_number": txn.remittance_reference or txn.reference_no,
			"transaction_id": txn.reference_no,
			"transaction_type": txn.subfamily_code or None,
			"bank_party_name": txn.party_name or None,
			"bank_party_iban": txn.party_iban or None,
			"deposit": amount if txn.direction == "CRDT" else 0,
			"withdrawal": amount if txn.direction == "DBIT" else 0,
			"included_fee": txn.charges,
		}
	)
	if plan and plan.party_type and plan.party:
		document.party_type, document.party = plan.party_type, plan.party
	document.insert(ignore_permissions=True)
	document.submit()
	return document


def enrich_bank_transaction(bank_transaction, plan, txn):
	"""Fill party/details on a Bank Transaction created before the plan was known."""
	if not bank_transaction:
		return
	bank_transaction.reload()
	description = get_full_remarks(plan, txn)
	changed = False
	if (
		plan.party_type
		and plan.party
		and (bank_transaction.party_type != plan.party_type or bank_transaction.party != plan.party)
	):
		bank_transaction.party_type, bank_transaction.party = plan.party_type, plan.party
		changed = True
	# Description is not editable after submit
	if bank_transaction.docstatus == 0 and description and bank_transaction.description != description:
		bank_transaction.description = description
		changed = True
	if changed:
		bank_transaction.save()


def create_payment_entry_from_plan(txn, plan, context, auto_submit):
	exchange_rate = get_exchange_rate_for_plan(plan, context.company, txn.date)
	data = {
		"doctype": "Payment Entry",
		"payment_type": plan.payment_type,
		"paid_amount": txn.amount,
		"received_amount": txn.amount,
		"reference_no": txn.reference_no,
		"reference_date": txn.date,
		"posting_date": txn.date,
		"remarks": get_full_remarks(plan, txn),
		"camt_amount": txn.amount,
		"bank_account_no": txn.party_iban,
		"company": context.company,
		"cost_center": plan.cost_center,
		"source_exchange_rate": exchange_rate,
		"target_exchange_rate": exchange_rate,
		"party_type": plan.party_type,
		"party": plan.party,
		"paid_from": plan.paid_from,
		"paid_to": plan.paid_to,
	}
	set_employee_payable_account(data, plan)
	entry = frappe.get_doc(data).insert()
	add_references(entry, plan.references, reference_doctype(plan))
	submitted = submit_payment_entry(entry.name) if auto_submit else False
	frappe.db.commit()
	return {
		"link": get_url_to_form("Payment Entry", entry.name),
		"payment_entry": entry.name,
		"submitted": submitted,
	}


def set_employee_payable_account(data, plan):
	if plan.payment_type != "Pay" or plan.party_type != "Employee":
		return
	settings = frappe.get_cached_doc("Lithuania Compliance Settings", "Lithuania Compliance Settings")
	account = None
	for row in settings.get("employee_payable_account_mapping") or []:
		if row.employee == plan.party:
			account = row.payable_account
			break
	if not account:
		account = settings.default_employee_payable_account
	if account:
		data["paid_to"] = account


def get_exchange_rate_for_plan(plan, company, date):
	account = plan.paid_to if plan.payment_type == "Receive" else plan.paid_from
	account_currency = frappe.get_value("Account", account, "account_currency")
	company_currency = frappe.get_value("Company", company, "default_currency")
	if not account_currency or account_currency == company_currency:
		return 1
	try:
		return get_exchange_rate(account_currency, company_currency, date) or 1
	except Exception:
		frappe.log_error("Bank Import exchange rate", frappe.get_traceback())
		return 1


def reference_doctype(plan) -> str | None:
	if not plan.references:
		return None
	if plan.payment_type == "Receive":
		return "Sales Invoice"
	if plan.party_type == "Employee" and frappe.db.exists("DocType", "Expense Claim"):
		return "Expense Claim"
	return "Purchase Invoice"


def add_references(payment_entry, references, doctype):
	if not doctype:
		return
	remaining = frappe.get_value("Payment Entry", payment_entry.name, "paid_amount")
	for name in references:
		total_field = "total_claimed_amount" if doctype == "Expense Claim" else "base_grand_total"
		outstanding_field = "total_claimed_amount" if doctype == "Expense Claim" else "outstanding_amount"
		outstanding = flt(frappe.get_value(doctype, name, outstanding_field))
		allocated = min(remaining, outstanding)
		payment_entry.append(
			"references",
			{
				"reference_doctype": doctype,
				"reference_name": name,
				"total_amount": frappe.get_value(doctype, name, total_field),
				"outstanding_amount": outstanding,
				"allocated_amount": allocated,
			},
		)
		remaining -= allocated
	payment_entry.save()


def submit_payment_entry(name) -> bool:
	try:
		entry = frappe.get_doc("Payment Entry", name)
		add_exchange_difference_deduction(entry)
		entry.submit()
		return True
	except Exception:
		frappe.log_error("Bank Import auto_submit", frappe.get_traceback())
		return False


def add_exchange_difference_deduction(entry):
	if not entry.difference_amount:
		return
	account = frappe.get_cached_value("Company", entry.company, "exchange_gain_loss_account")
	if not account:
		return
	deduction = {"account": account, "amount": entry.difference_amount}
	cost_center = frappe.get_cached_value("Company", entry.company, "round_off_cost_center")
	if cost_center:
		deduction["cost_center"] = cost_center
	entry.append("deductions", deduction)
	entry.save()


def create_cash_deposit_entry(txn, plan, context, auto_submit) -> tuple[str, bool]:
	entry = frappe.get_doc(
		{
			"doctype": "Journal Entry",
			"voucher_type": "Bank Entry",
			"posting_date": txn.date,
			"company": context.company,
			"cheque_no": txn.reference_no,
			"cheque_date": txn.date,
			"title": _("Cash Deposit"),
			"user_remark": get_full_remarks(plan, txn),
			"accounts": [
				{"account": plan.paid_to, "debit_in_account_currency": txn.amount},
				{
					"account": plan.paid_from,
					"credit_in_account_currency": txn.amount,
					"party_type": plan.party_type,
					"party": plan.party,
				},
			],
		}
	).insert()
	# validate() may overwrite the title for new docs, so force it after insert.
	frappe.db.set_value("Journal Entry", entry.name, "title", _("Cash Deposit"), update_modified=False)
	submitted = False
	if auto_submit:
		try:
			entry.submit()
			submitted = True
		except Exception:
			frappe.log_error("Bank Import CDPT", frappe.get_traceback())
	return entry.name, submitted


def create_fee_entry(txn, context, settings, bank_transaction, auto_submit):
	if not should_split_fee(txn, settings):
		return
	fee_plan = PostingPlan(
		"Internal Transfer",
		context.account,
		settings.bank_fee_expense_account,
		cost_center=settings.bank_fee_cost_center,
	)
	if txn.subfamily_code == "POSP" and settings.emv_account:
		fee_plan.paid_from = settings.emv_account
	fee_txn = CamtTransaction(
		**{**txn.__dict__, "amount": txn.charges, "reference_no": f"{txn.reference_no}-FEE", "charges": 0}
	)
	existing = find_existing_document(fee_txn, fee_plan, context.company)
	if existing:
		link_bank_transaction(bank_transaction, *existing, txn.charges)
		return
	result = create_payment_entry_from_plan(fee_txn, fee_plan, context, auto_submit)
	link_bank_transaction(bank_transaction, "Payment Entry", result["payment_entry"], txn.charges)


def should_split_fee(txn, settings) -> bool:
	return bool(txn.charges and settings.bank_fee_expense_account and txn.subfamily_code != "CHRG")


def link_bank_transaction(bank_transaction, document_type, document_name, amount):
	if not bank_transaction or not document_name:
		return
	bank_transaction.reload()
	if any(
		row.payment_document == document_type and row.payment_entry == document_name
		for row in bank_transaction.payment_entries
	):
		return
	bank_transaction.append(
		"payment_entries",
		{"payment_document": document_type, "payment_entry": document_name, "allocated_amount": amount},
	)
	bank_transaction.save()


def build_import_summary(results, company):
	records = [result.document_name for result in results if result.document_name]
	submitted = sum(result.submitted for result in results)
	reconciliations = create_reconciliation_documents(results, company)
	return {
		"message": _(
			"Checked {0} bank transactions. Created {1} payment entries ({2} submitted, {3} draft)"
		).format(len(results), len(records), submitted, len(records) - submitted),
		"records": records,
		"reconciliation_docs": reconciliations,
		"errors": [result.error for result in results if result.error],
	}


def create_reconciliation_documents(results, company):
	parties = {(result.party_type, result.party) for result in results if result.party_type and result.party}
	documents = []
	for party_type, party in parties:
		account = get_default_receivable_payable_account(party_type, party, company)
		if not account:
			continue
		document = frappe.get_doc(
			{
				"doctype": "Process Payment Reconciliation",
				"company": company,
				"party_type": party_type,
				"party": party,
				"receivable_payable_account": account,
			}
		)
		document.insert(ignore_permissions=True)
		documents.append(document.name)
	return documents


def get_or_create_party_from_iban(party_name, party_iban, is_credit, company=None):
	iban = (party_iban or "").replace(" ", "")
	existing = find_party_by_iban(iban, is_credit)
	if existing:
		return existing
	doctype, name_field = ("Customer", "customer_name") if is_credit else ("Supplier", "supplier_name")
	party = frappe.db.get_value(doctype, {name_field: party_name}, "name") if party_name else None
	auto_create = cint(
		frappe.get_cached_value(
			"Lithuania Compliance Settings", "Lithuania Compliance Settings", "auto_create_parties_from_iban"
		)
		or 0
	)
	if not party and auto_create and party_name:
		party = (
			frappe.get_doc({"doctype": doctype, name_field: normalize_reference(party_name)})
			.insert(ignore_permissions=True)
			.name
		)
	if party and auto_create and iban:
		create_party_bank_account(party, doctype, party_name, iban)
	return (doctype, party) if party else (None, None)


def find_party_by_iban(iban, is_credit):
	if not iban:
		return None
	rows = frappe.db.sql(
		"""
        SELECT party_type, party
        FROM `tabBank Account`
        WHERE disabled = 0
          AND REPLACE(COALESCE(iban, bank_account_no), ' ', '') = %(iban)s
        """,
		{"iban": iban},
		as_dict=True,
	)
	for row in rows:
		if row.party_type and row.party and (not is_credit or row.party_type == "Customer"):
			return row.party_type, row.party
	return None


def create_party_bank_account(party, doctype, party_name, iban):
	bank_name = "CAMT Imported Bank"
	bank = frappe.db.get_value("Bank", {"bank_name": bank_name}, "name")
	if not bank:
		bank = (
			frappe.get_doc({"doctype": "Bank", "bank_name": bank_name}).insert(ignore_permissions=True).name
		)
	if not frappe.db.exists("Bank Account", {"iban": iban, "party": party}):
		frappe.get_doc(
			{
				"doctype": "Bank Account",
				"account_name": f"{party_name or party} - {bank_name}",
				"bank": bank,
				"iban": iban,
				"party_type": doctype,
				"party": party,
				"is_company_account": 0,
			}
		).insert(ignore_permissions=True)


def get_company_account_by_iban(iban):
	if not iban:
		return None
	accounts = frappe.db.sql(
		"""
        SELECT account
        FROM `tabBank Account`
        WHERE is_company_account = 1
          AND disabled = 0
          AND account IS NOT NULL
          AND REPLACE(COALESCE(iban, bank_account_no), ' ', '') = %(iban)s
        LIMIT 1
        """,
		{"iban": iban.replace(" ", "")},
		as_dict=True,
	)
	return accounts[0].account if accounts else None


def get_account_by_structured_reference(reference, settings):
	if not reference:
		return None
	for row in settings.get("structured_reference_account_mapping") or []:
		if str(row.reference or "").strip() == str(reference).strip():
			return row.account
	return None


def find_supplier(name):
	normalized = normalize_reference(name)
	suppliers = frappe.get_all("Supplier", filters={"disabled": 0}, fields=["name", "supplier_name"])
	matches = [
		supplier.name for supplier in suppliers if normalize_reference(supplier.supplier_name) == normalized
	]
	return matches[0] if len(matches) == 1 else None


def get_employee(name):
	try:
		matches = frappe.get_all(
			"Employee", filters={"employee_name": name, "status": "Active"}, pluck="name"
		)
		return matches[0] if len(matches) == 1 else None
	except Exception:
		return None


def get_default_receivable_payable_account(party_type, party, company=None):
	if not party_type or not party:
		return None
	if company:
		return frappe.db.get_value(
			"Party Account", {"parent": party, "parenttype": party_type, "company": company}, "account"
		)
	# Fallback to first matching party account
	return frappe.db.get_value("Party Account", {"parent": party, "parenttype": party_type}, "account")


def get_full_remarks(plan, txn):
	if plan.payment_type == "Receive" and plan.party_type == "Customer":
		title = _("Receipt from {0}").format(txn.party_name or plan.party)
	elif plan.payment_type == "Receive":
		title = _("Cash deposit into bank account") if txn.subfamily_code == "CDPT" else _("Bank receipt")
	elif plan.payment_type == "Pay" and plan.party_type == "Supplier":
		title = _("Payment to supplier {0}").format(txn.party_name or plan.party)
	elif plan.payment_type == "Pay" and plan.party_type == "Employee":
		title = _("Payment to employee {0}").format(txn.party_name or plan.party)
	elif txn.subfamily_code == "CHRG":
		title = _("Bank fee (charges)")
	else:
		title = _("Cash deposit transfer") if txn.subfamily_code == "CDPT" else ""
	return (
		f"{title}: {txn.remittance_reference}"
		if title and txn.remittance_reference
		else title or txn.remittance_reference
	)


def normalize_reference(value):
	return re.sub(r"[\s\-\"'/\\]", "", value or "")


def numeric_reference(value):
	return "".join(character for character in str(value) if character.isdigit())
