# `read_camt_transactions` and some other snippets are adapted from https://github.com/libracore/erpnextswiss
#! The file requires further refactoring to improve structure. It is awfully nested!
# TODO: Cost center setting
# TODO: a friendly list of imported operations in the frontend
# TODO: a dialog to ask should payment auto reconciliation should be enqueued.
import ast
import datetime
import hashlib
import re

import frappe
from bs4 import BeautifulSoup
from erpnext.setup.utils import get_exchange_rate
from frappe import _
from frappe.utils import cint, flt
from frappe.utils.data import get_url_to_form

# Swedbank uses ISO_XML_052 (ISO 20022 CAMT052)


def remove_special_characters(s):
	return re.sub(r'[\s\-"\'/\\]', "", s or "")


def get_default_receivable_payable_account(party_type, party):
	"""Get default receivable/payable account from party."""
	try:
		if party_type == "Supplier":
			return frappe.get_value("Supplier", party, "payable_account")
		elif party_type == "Customer":
			return frappe.get_value("Customer", party, "receivable_account")
	except Exception:
		pass
	return None


def get_full_remarks(payment_type, party_type, party_name, party, subfamily_code, remarks):
	title = None
	if payment_type == "Receive" and party_type == "Customer" and (party_name or party):
		title = _("Receipt from {0}").format(party_name or party)
	elif payment_type == "Receive" and subfamily_code == "CDPT":
		title = _("Cash deposit into bank account")
	elif payment_type == "Receive":
		title = _("Bank receipt")
	elif payment_type == "Pay" and party_type == "Supplier" and (party_name or party):
		title = _("Payment to supplier {0}").format(party_name or party)
	elif payment_type == "Pay" and party_type == "Employee" and (party_name or party):
		title = _("Payment to employee {0}").format(party_name or party)
	elif payment_type == "Pay":
		title = _("Bank payment")
	elif subfamily_code == "CHRG":
		title = _("Bank fee (charges)")
	elif subfamily_code == "CDPT":
		title = _("Cash deposit transfer")
	else:
		return remarks

	return f"{title}: {remarks}" if remarks else title


def match_by_amount(amount):
	sql_query = """
		SELECT `name`
		FROM `tabSales Invoice`
		WHERE `docstatus` = 1
		AND `grand_total` = {0}
		AND `status` != 'Paid'; """.format(amount)
	open_sales_invoices = frappe.db.sql(sql_query, as_dict=True)
	if open_sales_invoices and len(open_sales_invoices) == 1:
		return open_sales_invoices[0].name
	else:
		return None


def match_by_comment(comment):  # Can be used for matching reference numbers in comments
	sql_query = """
		SELECT `name`
		FROM `tabSales Invoice`
		WHERE `docstatus` = 1
		AND `status` != 'Paid';"""
	open_sales_invoices = frappe.db.sql(sql_query, as_dict=True)

	if not open_sales_invoices:
		return None

	for reference in open_sales_invoices.name:
		if reference in comment:
			return reference


def get_supplier_erpnext_name(name):
	# Remove quotes from name for matching
	cleaned_name = remove_special_characters(name).strip()
	sql_query = """
		SELECT `name`
		FROM `tabSupplier`
		WHERE REPLACE(REPLACE(`supplier_name`, '"', ''), "'", '') = '{0}'
		AND `disabled` = 0; """.format(cleaned_name)
	suppliers = frappe.db.sql(sql_query, as_dict=True)
	if suppliers and len(suppliers) == 1:
		return suppliers[0].name
	else:
		return None


def get_employee(name):
	employees = []
	try:
		employees = frappe.get_all(
			"Employee",
			filters={"employee_name": name, "status": "active"},
			fields=["name"],
		)
	except Exception:
		# "Employee" DocType might not be available
		return None
	if employees and len(employees) == 1:
		return employees[0]["name"]
	else:
		return None


def get_company_account_by_iban(iban):
	try:
		accounts = frappe.db.sql(
			"""
			SELECT `account` AS `name`
			FROM `tabBank Account`
			WHERE `is_company_account` = 1
				AND `disabled` = 0
				AND `account` IS NOT NULL
				AND REPLACE(COALESCE(`bank_account_no`, `iban`), ' ', '') = %(iban)s
			""",
			{"iban": iban.replace(" ", "")},
			as_dict=True,
		)
	except Exception:
		accounts = []

	return accounts[0]["name"] if accounts else None


def get_account_by_structured_reference(structured_reference, settings):
	"""Resolve an Account from a structured creditor reference (CdtrRefInf/Ref).

	The mapping is maintained on Lithuania Compliance Settings as a child table
	"structured_reference_account_mapping" (DocType "Structured Reference Account Mapping").
	Only exact matches on the reference value are considered.
	"""

	if not structured_reference:
		return None

	# Child table rows are available as a list-like attribute on the settings doc
	rows = getattr(settings, "structured_reference_account_mapping", None) or []
	for row in rows:
		# Simple exact match; references in CAMT files are already strings
		if frappe.as_unicode(row.reference or "").strip() == frappe.as_unicode(structured_reference).strip():
			return row.account

	return None


def get_unpaid_sales_invoices_by_customer(customer):
	sql_query = """
		SELECT `name`
		FROM `tabSales Invoice`
		WHERE `docstatus` = 1
		AND `customer` = '{0}'
		AND `status` != 'Paid'; """.format(customer)
	return frappe.db.sql(sql_query, as_dict=True)


def log(comment):
	new_comment = frappe.get_doc({"doctype": "Log"})
	new_comment.comment = comment
	new_comment.insert()
	return new_comment


def get_or_create_party_from_iban(party_name, party_iban, is_credit, company=None):
	"""
	Match or create party & Bank Account from IBAN and party name.

	- First, try to find an existing Bank Account with this IBAN that has
	  party_type and party set; if found, return that.
	- Otherwise, infer party type from transaction direction
	  (CRDT -> Customer, DBIT -> Supplier), look up by name, and if not
	  found, create a new Customer/Supplier.
	- For a resolved party, create a Bank Account record with the IBAN
	"""

	iban = (party_iban or "").replace(" ", "")
	if not iban and not party_name:
		return (None, None)

	# Check setting if we are allowed to auto-create parties/bank accounts
	auto_create = cint(
		frappe.get_value(
			"Lithuania Compliance Settings",
			"Lithuania Compliance Settings",
			"auto_create_parties_from_iban",
		)
		or 0
	)

	party_result = frappe.db.get_all(
		"Bank Account",
		filters={"disabled": 0, "bank_account_no": iban},
		fields=["party_type", "party"],
		limit_page_length=1,
	)
	if not party_result:
		party_result = frappe.db.get_all(
			"Bank Account",
			filters={"disabled": 0, "iban": iban},
			fields=["party_type", "party"],
			limit_page_length=1,
		)
	if party_result:
		row = party_result[0]
		# For incoming money, always use Customer type. If the
		# existing Bank Account is linked to a Supplier/Employee,
		# ignore it and fall back to Customer resolution.
		if row.get("party_type") and row.get("party") and (not is_credit or row["party_type"] == "Customer"):
			return (row["party_type"], row["party"])

	if is_credit:
		primary_doctype = "Customer"
		name_field = "customer_name"
	else:
		primary_doctype = "Supplier"
		name_field = "supplier_name"

	party = None

	if party_name:
		# Try to find existing party by its display name
		existing = frappe.get_all(
			primary_doctype,
			filters={name_field: party_name},
			fields=["name"],
			limit_page_length=1,
		)
		if existing:
			party = existing[0]["name"]
		elif auto_create:
			# Create a new Customer/Supplier with this name
			# TODO: settings whether to auto-create Customers or Suppliers
			try:
				doc = frappe.get_doc(
					{
						"doctype": primary_doctype,
						name_field: remove_special_characters(party_name).strip(),
					}
				)
				doc.insert(ignore_permissions=True)
				party = doc.name
			except Exception as err:
				frappe.log_error("Bank Import: create party from IBAN", str(err))

	if not party:
		return (None, None)

	# TODO: add extra field for default Bank name
	if auto_create and iban:
		try:
			bank_name = "CAMT Imported Bank"
			bank = frappe.db.get_value("Bank", {"bank_name": bank_name}, "name")
			if not bank:
				bank_doc = frappe.get_doc({"doctype": "Bank", "bank_name": bank_name})
				bank_doc.insert(ignore_permissions=True)
				bank = bank_doc.name

			account_name = f"{party_name or party} - {bank_name}"
			bank_account_doc = frappe.get_doc(
				{
					"doctype": "Bank Account",
					"account_name": account_name,
					"bank": bank,
					"bank_account_no": iban,
					"party_type": primary_doctype,
					"party": party,
					"is_company_account": 0,
				}
			)
			bank_account_doc.insert(ignore_permissions=True)
		except Exception as err:
			frappe.log_error("Bank Import: create bank account from IBAN", str(err))

	return (primary_doctype, party)


# NOTE: this is a hell of a function and needs a lot of refactoring when it comes to try/except blocks
def read_camt_transactions(
	transaction_entries,
	account,
	settings,
	skip_existing_payment_entries=True,
):
	company = frappe.get_value("Account", account, "company")
	txns = []
	for entry in transaction_entries:
		entry_soup = BeautifulSoup(str(entry), "lxml")
		if entry_soup.bookgdt.dt:
			date = entry_soup.bookgdt.dt.get_text()[:10]
		elif entry_soup.bookgdt.dttm:
			date = entry_soup.bookgdt.dttm.get_text()[:10]
		else:
			date = datetime.datetime.today().strftime("%Y-%m-%d")
		transactions = entry_soup.find_all("txdtls")
		# fetch entry amount as fallback
		entry_amount = float(entry_soup.amt.get_text())
		entry_currency = entry_soup.amt["ccy"]
		# fetch global account service reference
		global_account_service_reference = entry_soup.acctsvcrref.get_text() if entry_soup.acctsvcrref else ""
		transaction_count = 0

		if not transactions and len(transactions) <= 0:
			return

		for transaction in transactions:
			transaction_count += 1
			transaction_soup = BeautifulSoup(str(transaction), "lxml")
			always_use_entry = getattr(settings, "always_use_entry_transaction_type", 0)
			if always_use_entry:
				credit_debit = entry_soup.cdtdbtind.get_text()
			else:
				credit_debit = (
					transaction_soup.cdtdbtind.get_text()
					if transaction_soup.cdtdbtind
					else entry_soup.cdtdbtind.get_text()
				)

			# payment_instruction_id = (
			# 	transaction_soup.pmtinfid.get_text() if transaction_soup.pmtinfid else None
			# )

			# --- find unique reference
			unique_reference = ""
			try:
				# try to use the unique end-to-end transaction reference
				unique_reference = transaction_soup.txdtls.refs.uetr.get_text()
			except:
				try:
					# try to use the account service reference
					unique_reference = transaction_soup.txdtls.refs.acctsvcrref.get_text()
				except:
					# fallback: use tx id
					try:
						unique_reference = transaction_soup.txid.get_text()
					except:
						# fallback to pmtinfid
						try:
							unique_reference = transaction_soup.pmtinfid.get_text()
						except:
							try:
								if entry_soup.ntryref:
									unique_reference = entry_soup.ntryref.get_text()
								elif global_account_service_reference != "":
									# fallback to group account service reference plus transaction_count
									unique_reference = "{0}-{1}".format(
										global_account_service_reference, transaction_count
									)
								else:
									# fallback ntry reference or booking code (wise) (for banks this is often not unique)
									unique_reference = entry_soup.bktxcd.prtry.cd.get_text()
							except:
								# fallback to ustrd (do not use)
								# unique_reference = transaction_soup.ustrd.get_text()
								# fallback to hash
								amount = transaction_soup.txdtls.amt.get_text()
								party = transaction_soup.nm.get_text()
								code = "{0}:{1}:{2}".format(date, amount, party)
								unique_reference = hashlib.md5(code.encode("utf-8")).hexdigest()
			# --- find amount and currency
			try:
				# try to find as <TxAmt>
				amount = float(transaction_soup.txdtls.txamt.amt.get_text())
				currency = transaction_soup.txdtls.txamt.amt["ccy"]
			except:
				try:
					# fallback to pure <AMT>
					amount = float(transaction_soup.txdtls.amt.get_text())
					currency = transaction_soup.txdtls.amt["ccy"]
				except:
					# fallback to amount from entry level
					amount = entry_amount
					currency = entry_currency
			# --- transaction sub-family code (e.g. CHRG for bank charges)
			try:
				subfamily_code = entry_soup.bktxcd.domn.fmly.subfmlycd.get_text()
			except:
				subfamily_code = ""
			try:
				# --- find party IBAN
				if credit_debit == "DBIT":
					# use RltdPties:Cdtr
					party_soup = BeautifulSoup(str(transaction_soup.txdtls.rltdpties.cdtr), "lxml")
					try:
						party_iban = transaction_soup.cdtracct.id.iban.get_text()
					except:
						party_iban = ""
				else:
					# CRDT: use RltdPties:Dbtr
					party_soup = BeautifulSoup(str(transaction_soup.txdtls.rltdpties.dbtr), "lxml")
					try:
						party_iban = transaction_soup.dbtracct.id.iban.get_text()
					except:
						party_iban = ""
				try:
					party_name = party_soup.nm.get_text()
					if party_soup.strtnm:
						# parse by street name, ...
						try:
							street = party_soup.strtnm.get_text()
							try:
								street_number = party_soup.bldgnb.get_text()
								address_line1 = "{0} {1}".format(street, street_number)
							except:
								address_line1 = street

						except:
							address_line1 = ""
						try:
							plz = party_soup.pstcd.get_text()
						except:
							plz = ""
						try:
							town = party_soup.twnnm.get_text()
						except:
							town = ""
						address_line2 = "{0} {1}".format(plz, town)
					else:
						# parse by address lines
						try:
							address_lines = party_soup.find_all("adrline")
							address_line1 = address_lines[0].get_text()
							address_line2 = address_lines[1].get_text()
						except:
							# in case no address is provided
							address_line1 = ""
							address_line2 = ""
				except:
					# party is not defined (e.g. DBIT from Bank)
					try:
						address_lines = party_soup.find_all("adrline")
						party_name = address_lines[0].get_text()
					except:
						party_name = ""
					address_line1 = ""
					address_line2 = ""
				try:
					country = party_soup.ctry.get_text()
				except:
					country = ""
				if (address_line1 != "") and (address_line2 != ""):
					party_address = "{0}, {1}, {2}".format(address_line1, address_line2, country)
				elif address_line1 != "":
					party_address = "{0}, {1}".format(address_line1, country)
				else:
					party_address = "{0}".format(country)
			except:
				# key related parties not found / no customer info
				party_name = ""
				party_address = ""
				party_iban = ""
			# Bank charges and taxes that are reported on transaction level.
			# Swedbank may use either
			#   <Chrgs><TtlChrgsAndTaxAmt><Amt>...</Amt></TtlChrgsAndTaxAmt></Chrgs>
			# or a simpler <Chrgs><Amt>...</Amt></Chrgs> structure.
			charges = 0.0
			charges_tag = None
			try:
				charges_tag = transaction_soup.chrgs.ttlchrgsandtaxamt
			except Exception:
				charges_tag = None
			if not charges_tag:
				try:
					charges_tag = transaction_soup.chrgs.amt
				except Exception:
					charges_tag = None
			if charges_tag:
				try:
					charges = float(charges_tag.get_text())
				except Exception:
					charges = 0.0

			structured_reference = None
			try:
				# Try to find a structured creditor reference (SCOR, CdtrRefInf/Ref)
				structured_reference = transaction_soup.rmtinf.strd.cdtrrefinf.ref.get_text()
			except Exception:
				structured_reference = None

			if structured_reference:
				# Prefer structured reference when available
				transaction_reference = structured_reference
			else:
				try:
					try:
						transaction_reference = transaction_soup.rmtinf.ustrd.get_text()
					except:
						try:
							transaction_reference = transaction_soup.endtoendid.get_text()
						except:
							transaction_reference = transaction_soup.addtltxinf.get_text()
				except Exception:
					# As a last resort, use the unique reference
					transaction_reference = unique_reference

			# Check if this transaction already has a Payment Entry recorded.
			# We want a Bank Transaction per statement line anyways
			_filters = {"reference_no": unique_reference, "company": company}
			match_payment_entry = frappe.get_all(
				"Payment Entry",
				filters=_filters,
				fields=["name"],
			)
			if skip_existing_payment_entries and match_payment_entry:
				continue

			# try to find matching parties & invoices
			party_match = None
			employee_match = None
			invoice_matches = []
			expense_matches = None
			matched_amount = 0.0
			if credit_debit == "DBIT":
				# find supplier from name (e.g. '"Swedbank", AB').
				party_match = get_supplier_erpnext_name(party_name)
				employee_match = get_employee(party_name)
			else:
				# customers & sales invoices
				match_customers = frappe.get_all(
					"Customer", filters={"customer_name": party_name, "disabled": 0}, fields=["name"]
				)
				if match_customers:
					party_match = match_customers[0]["name"]
				# sales invoices (no ESR-specific field)
				possible_sinvs = frappe.get_all(
					"Sales Invoice",
					filters=[["outstanding_amount", ">", 0], ["docstatus", "=", 1]],
					fields=["name", "customer", "customer_name", "outstanding_amount"],
				)
				if possible_sinvs:
					invoice_matches = []
					for sinv in possible_sinvs:
						is_match = False
						if sinv["name"] in transaction_reference:
							is_match = True
						elif cint(settings.numeric_only_debtor_matching) == 1:
							# allow the numeric part matching
							if get_numeric_only_reference(sinv["name"]) in transaction_reference:
								# matched numeric part and customer name
								is_match = True
						elif cint(settings.ignore_special_characters) == 1:
							if remove_special_characters(sinv["name"]) in remove_special_characters(
								transaction_reference
							):
								# matched without special characters
								is_match = True

						if is_match:
							invoice_matches.append(sinv["name"])
							party_match = sinv["customer"]
							# add total matched amount
							matched_amount += float(sinv["outstanding_amount"])

			# reset invoice matches in case there are no matches
			try:
				if len(invoice_matches) == 0:
					invoice_matches = None
				if len(expense_matches) == 0:
					expense_matches = None
			except:
				pass
			new_txn = {
				"txid": len(txns),
				"date": date,
				"currency": currency,
				"amount": amount,
				"charges": charges,
				"party_name": party_name,
				"party_address": party_address,
				"credit_debit": credit_debit,
				"party_iban": party_iban,
				"unique_reference": unique_reference,
				"structured_reference": structured_reference,
				"transaction_reference": transaction_reference,
				"subfamily_code": subfamily_code,
				"party_match": party_match,
				"invoice_matches": invoice_matches,
				"matched_amount": round(matched_amount, 2),
				"employee_match": employee_match,
				"expense_matches": expense_matches,
			}
			txns.append(new_txn)

	return txns


#! This is another ugly function; requires a lot of refactoring;
@frappe.whitelist()
def read_camt054(content, account=None, auto_submit=False):
	"""Import a CAMT.052/054 XML file and create draft Payment Entries.

	Swedbank and other banks often deliver CAMT.052 account reports
	under various labels (including CAMT.054).
	ISO 20022 structure (BkToCstmrAcctRpt / BkToCstmrStmt),
	"""

	settings = frappe.get_doc("Lithuania Compliance Settings", "Lithuania Compliance Settings")

	soup = BeautifulSoup(content, "lxml")

	# Try to resolve bank account from the CAMT header (IBAN) if not
	# explicitly provided. Support both CAMT.052 (BkToCstmrAcctRpt)
	# and CAMT.053 (BkToCstmrStmt) structures.

	if not account:
		iban = None
		# CAMT.052: Document/BkToCstmrAcctRpt/Rpt/Acct/Id/IBAN
		try:
			iban = soup.document.bktocstmracctrpt.rpt.acct.id.iban.get_text()
		except Exception:
			pass

		# Fallback to CAMT.053 structure if 052-specific path not found
		if not iban:
			try:
				iban = soup.document.bktocstmrstmt.stmt.acct.id.iban.get_text()
			except Exception:
				pass

		if not iban:
			frappe.msgprint(
				_("Cannot find IBAN in CAMT.052/054 file."),
				_("Bank Import IBAN validation"),
			)
			frappe.throw(_("IBAN not found in CAMT file"))

		# Find GL account by IBAN
		account = get_company_account_by_iban(iban)

		if not account:
			frappe.msgprint(
				_(
					"No account found for IBAN {0}. Make sure there is an account in the chart of accounts with this IBAN, account type Bank and not disabled."
				).format(iban),
				_("Bank Import IBAN validation"),
			)
			frappe.throw(_("Bank account not found for IBAN"))

	company = None
	bank_account_name = None

	if account:
		company = frappe.get_value("Account", account, "company")
		bank_account_name = frappe.db.get_value(
			"Bank Account",
			{"account": account, "is_company_account": 1, "disabled": 0},
			"name",
		)

	# Collect all Ntry elements and let the existing matcher build
	# transaction dictionaries (amount, party, matches, patterns, ...).
	entries = soup.find_all("ntry")
	# For CAMT.052/054 imports we always want a Bank Transaction
	# per statement line, even if a Payment Entry already exists.
	transactions = read_camt_transactions(
		entries,
		account,
		settings,
		skip_existing_payment_entries=False,
	)

	auto_submit_flag = False
	if str(auto_submit) in ("1", "true", "True"):
		auto_submit_flag = True

	created_entries = []
	collected_parties = {}  # {(party_type, party): {'count': n, 'account': account}}

	for txn in transactions:
		try:
			is_credit = txn.get("credit_debit") == "CRDT"
			amount = float(txn.get("amount") or 0)
			if not amount:
				continue

			charges = flt(txn.get("charges") or 0)

			date = txn.get("date")
			reference_no = txn.get("unique_reference")
			remarks = txn.get("transaction_reference")
			structured_reference = txn.get("structured_reference")
			party_iban = txn.get("party_iban")
			party_name = txn.get("party_name")
			pattern = txn.get("pattern")
			subfamily_code = (txn.get("subfamily_code") or "").upper()
			currency = txn.get("currency")

			party = None
			party_type = None
			references = None
			paid_from = None
			paid_to = None
			payment_type = None

			matched_party_type = None
			matched_party = None
			if party_iban or party_name:
				try:
					matched_party_type, matched_party = get_or_create_party_from_iban(
						party_name, party_iban, is_credit, company
					)
				except Exception as err:
					frappe.log_error(
						"Bank Import CAMT.052 get_or_create_party_from_iban Error",
						f"get_or_create_party_from_iban failed, IBAN {party_iban} and name {party_name}: {err}",
					)

			# If we have a structured creditor reference, try to resolve a
			# mapped GL account from settings. This is only applied for
			# structured references; unstructured (Ustrd) references are
			# intentionally ignored for this mapping.
			mapped_account = get_account_by_structured_reference(structured_reference, settings)

			if is_credit:
				invoice_matches = txn.get("invoice_matches") or []
				party_match = txn.get("party_match")
				paid_to = account

				# Structured reference mapping: treat as internal transfer from
				# the mapped account into the bank account.
				if mapped_account and account:
					payment_type = "Internal Transfer"
					paid_from = mapped_account
					party_type = None
					party = None
				# Cash deposits
				elif subfamily_code == "CDPT" and account and settings.cash_deposit_account:
					payment_type = "Internal Transfer"
					paid_from = settings.cash_deposit_account
					party_type = None
					party = None
				# EMV/POS settlements
				elif subfamily_code == "POSP" and account and settings.emv_account:
					auto_submit_flag = False
					payment_type = "Internal Transfer"
					paid_from = settings.emv_account
					party_type = None
					party = None
				elif subfamily_code == "BOOK" and account and party_iban:
					source_account = get_company_account_by_iban(party_iban)
					# Only treat as internal transfer if both accounts belong to the same company and are company accounts
					if source_account and source_account != account:
						source_company = frappe.get_value("Account", source_account, "company")
						if source_company == company:
							# Verify both are company accounts
							is_source_company_account = frappe.db.exists(
								"Bank Account",
								{"account": source_account, "is_company_account": 1, "disabled": 0},
							)
							is_target_company_account = frappe.db.exists(
								"Bank Account", {"account": account, "is_company_account": 1, "disabled": 0}
							)
							if is_source_company_account and is_target_company_account:
								payment_type = "Internal Transfer"
								paid_from = source_account
								party_type = None
								party = None
				else:  # Regular incoming money
					payment_type = "Receive"

				if payment_type == "Receive":
					if invoice_matches:
						# Use customer from first matched Sales Invoice
						inv_name = invoice_matches[0]
						party_type = "Customer"
						party = frappe.get_value("Sales Invoice", inv_name, "customer")
						references = invoice_matches
					elif matched_party_type and matched_party:
						# Fallback to IBAN-based party (could be Customer or Supplier)
						party_type = matched_party_type
						party = matched_party
					elif party_match:
						party_type = "Customer"
						party = party_match
					else:
						# No party/invoice: route to deposit account if configured,
						# otherwise use the generic default customer.
						# deposit_account = get_deposit_account().get('account')
						if settings.cash_deposit_account and account:
							payment_type = "Internal Transfer"
							paid_from = account
							paid_to = settings.cash_deposit_account
							party_type = None
							party = None
						else:
							party_type = "Customer"
							party = settings.default_customer

			else:  # Debit: outgoing money
				invoice_matches = txn.get("invoice_matches") or []
				expense_matches = txn.get("expense_matches") or []
				employee_match = txn.get("employee_match")
				party_match = txn.get("party_match")
				subfamily_code = (txn.get("subfamily_code") or "").upper()

				# Structured reference mapping: treat as internal transfer from
				# the bank account into the mapped account.
				if mapped_account and account:
					payment_type = "Internal Transfer"
					paid_from = account
					paid_to = mapped_account
					party_type = None
					party = None
				# Bank charges SubFmlyCd = CHRG
				elif settings.bank_fee_expense_account and subfamily_code == "CHRG":
					payment_type = "Internal Transfer"
					paid_from = account
					paid_to = settings.bank_fee_expense_account
					party_type = None
					party = None
				elif subfamily_code == "BOOK" and account and party_iban:
					target_account = get_company_account_by_iban(party_iban)
					# Only treat as internal transfer if both accounts belong to the same company and are company accounts
					if target_account and target_account != account:
						target_company = frappe.get_value("Account", target_account, "company")
						if target_company == company:
							# Verify both are company accounts
							is_target_company_account = frappe.db.exists(
								"Bank Account",
								{"account": target_account, "is_company_account": 1, "disabled": 0},
							)
							is_source_company_account = frappe.db.exists(
								"Bank Account", {"account": account, "is_company_account": 1, "disabled": 0}
							)
							if is_target_company_account and is_source_company_account:
								payment_type = "Internal Transfer"
								paid_from = account
								paid_to = target_account
								party_type = None
								party = None

				# Regular matching
				if payment_type is None and expense_matches and employee_match:
					payment_type = "Pay"
					paid_from = account
					party_type = "Employee"
					party = employee_match
					references = expense_matches
				elif payment_type is None and invoice_matches:
					payment_type = "Pay"
					paid_from = account
					party_type = "Supplier"
					pinv_name = invoice_matches[0]
					party = frappe.get_value("Purchase Invoice", pinv_name, "supplier")
					references = invoice_matches
				elif payment_type is None and employee_match:
					payment_type = "Pay"
					paid_from = account
					party_type = "Employee"
					party = employee_match
				elif payment_type is None and matched_party_type and matched_party:
					payment_type = "Pay"
					paid_from = account
					party_type = matched_party_type
					party = matched_party
				elif payment_type is None and party_match:
					payment_type = "Pay"
					paid_from = account
					party_type = "Supplier"
					party = party_match

			remarks = get_full_remarks(
				payment_type,
				party_type,
				party_name,
				party,
				subfamily_code,
				remarks,
			)
			# Create or reuse a Bank Transaction representing this statement line
			# might reuse since if user re-imports when automatic party creation is switched off, they created bank accounts manually
			bank_transaction = None
			if bank_account_name:
				try:
					existing_bt_name = None
					if reference_no:
						existing_bt_name = frappe.db.get_value(
							"Bank Transaction",
							{"bank_account": bank_account_name, "transaction_id": reference_no},
							"name",
						)

					if existing_bt_name:
						bank_transaction = frappe.get_doc("Bank Transaction", existing_bt_name)
					else:
						# If we are going to split out bank charges into a
						# separate Payment Entry, the Bank Transaction should
						# reflect the total movement (base amount + charges) so
						# both Payment Entries can fully reconcile it.
						use_fee_split = (
							charges > 0
							and bool(settings.bank_fee_expense_account)
							and bool(account)
							and subfamily_code != "CHRG"
						)
						gross_amount = amount + charges if use_fee_split else amount

						deposit = gross_amount if is_credit else 0.0
						withdrawal = gross_amount if not is_credit else 0.0

						description = remarks or txn.get("transaction_reference") or ""
						reference_number = txn.get("transaction_reference") or reference_no

						bank_transaction = frappe.get_doc(
							{
								"doctype": "Bank Transaction",
								"bank_account": bank_account_name,
								"date": date,
								"currency": currency,
								"description": description,
								"reference_number": reference_number,
								"transaction_id": reference_no,
								"transaction_type": subfamily_code or None,
								"bank_party_name": party_name or None,
								"bank_party_iban": party_iban or None,
								"deposit": deposit,
								"withdrawal": withdrawal,
								"included_fee": charges or 0.0,
							}
						)

						if party_type and party:
							bank_transaction.party_type = party_type
							bank_transaction.party = party

						bank_transaction.insert(ignore_permissions=True)
						bank_transaction.submit()
				except Exception as bt_err:
					frappe.log_error(
						"Bank Import CAMT.052 Error",
						f"Failed to create Bank Transaction for {reference_no}: {bt_err}",
					)
					bank_transaction = None

			# If we could not resolve a proper GL accounts, skip it
			if payment_type == "Receive" and not paid_to:
				continue
			if payment_type == "Pay" and not paid_from:
				continue
			if payment_type == "Internal Transfer" and (not paid_from or not paid_to):
				continue

			# If a Payment Entry with this reference already exists / created manually by a user, do not create another one.
			existing_payment_entry_name = None
			try:
				# For internal transfers with matching accounts and amount, we can match without reference_no
				# Especially transfer between company accounts (prone to duplicate entries)
				if payment_type == "Internal Transfer" and paid_from and paid_to and amount > 100:
					existing_payment_entry_name = frappe.db.get_value(
						"Payment Entry",
						{
							"payment_type": "Internal Transfer",
							"paid_from": paid_from,
							"paid_to": paid_to,
							"paid_amount": amount,
							"posting_date": date,
						},
						"name",
					)
				elif reference_no and company:
					existing_payment_entry_name = frappe.db.get_value(
						"Payment Entry", {"reference_no": reference_no, "company": company}, "name"
					)
				elif reference_no:
					existing_payment_entry_name = frappe.db.get_value(
						"Payment Entry", {"reference_no": reference_no}, "name"
					)

			except Exception as pe_lookup_err:
				frappe.log_error(
					"Bank Import CAMT.052 Error",
					f"Failed to look up existing Payment Entry for {reference_no}: {pe_lookup_err}",
				)

			if existing_payment_entry_name and bank_transaction:
				try:
					bank_transaction.reload()
					if not any(
						pe.payment_entry == existing_payment_entry_name
						for pe in bank_transaction.get("payment_entries", [])
					):
						bank_transaction.append(
							"payment_entries",
							{
								"payment_document": "Payment Entry",
								"payment_entry": existing_payment_entry_name,
								"allocated_amount": amount,
							},
						)
						bank_transaction.save()
				except Exception as link_existing_err:
					frappe.log_error(
						"Bank Import CAMT.052 Error",
						f"Failed to link existing Payment Entry {existing_payment_entry_name} to Bank Transaction {bank_transaction.name}: {link_existing_err}",
					)

			if existing_payment_entry_name:
				continue

			# Serialise references for make_payment_entry, needs to be a string
			references_param = None
			if references:
				references_param = str(references)

			result = make_payment_entry(
				amount=amount,
				date=date,
				reference_no=reference_no,
				paid_from=paid_from,
				paid_to=paid_to,
				type=payment_type,
				party=party,
				party_type=party_type,
				references=references_param,
				remarks=remarks,
				auto_submit=1 if auto_submit_flag else 0,
				party_iban=party_iban,
				company=company,
				pattern=pattern,
			)

			if result and result.get("payment_entry"):
				pe_name = result["payment_entry"]
				created_entries.append(pe_name)

				# Collect party information for Process Payment Reconciliation
				if party_type and party and payment_type in ("Pay", "Receive"):
					party_key = (party_type, party)
					if party_key not in collected_parties:
						account = get_default_receivable_payable_account(party_type, party)
						collected_parties[party_key] = {"count": 1, "account": account}
					else:
						collected_parties[party_key]["count"] += 1

				# Link the created Payment Entry back to the Bank Transaction
				if bank_transaction:
					try:
						bank_transaction.reload()
						# Check if already allocated
						if not any(
							pe.payment_entry == pe_name for pe in bank_transaction.get("payment_entries", [])
						):
							bank_transaction.append(
								"payment_entries",
								{
									"payment_document": "Payment Entry",
									"payment_entry": pe_name,
									"allocated_amount": amount,
								},
							)
							bank_transaction.save()
					except Exception as link_err:
						frappe.log_error(
							"Bank Import CAMT.052 Error",
							f"Failed to link Payment Entry {pe_name} to Bank Transaction {bank_transaction.name}: {link_err}",
						)

				# If there are transaction-level bank charges and a default
				# bank fee expense account is configured, create a separate
				# Payment Entry for the fee.
				if (
					charges
					and charges > 0
					and settings.bank_fee_expense_account
					and account
					and subfamily_code != "CHRG"
				):
					try:
						fee_reference_no = f"{reference_no}-FEE" if reference_no else None
						fee_remarks = _("Bank charges for {0}").format(reference_no or date)

						fee_result = make_payment_entry(
							amount=charges,
							date=date,
							reference_no=fee_reference_no,
							paid_from=settings.emv_account
							if subfamily_code == "POSP" and settings.emv_account
							else account,
							paid_to=settings.bank_fee_expense_account,
							type="Internal Transfer",
							party=None,
							party_type=None,
							references=None,
							remarks=fee_remarks,
							auto_submit=1 if auto_submit_flag else 0,
							party_iban=party_iban,
							company=company,
							pattern=None,
						)

						if fee_result and fee_result.get("payment_entry"):
							fee_pe_name = fee_result["payment_entry"]
							created_entries.append(fee_pe_name)

							# Link the fee Payment Entry back to the same
							# Bank Transaction so that the sum of allocated
							# amounts (main + fee) matches the Bank
							# Transaction amount for reconciliation.
							if bank_transaction:
								try:
									bank_transaction.reload()
									# Check if already allocated
									if not any(
										pe.payment_entry == fee_pe_name
										for pe in bank_transaction.get("payment_entries", [])
									):
										bank_transaction.append(
											"payment_entries",
											{
												"payment_document": "Payment Entry",
												"payment_entry": fee_pe_name,
												"allocated_amount": charges,
											},
										)
										bank_transaction.save()
								except Exception as fee_link_err:
									frappe.log_error(
										"Bank Import CAMT.052 Error",
										f"Failed to link Bank Fee Payment Entry {fee_pe_name} to Bank Transaction {bank_transaction.name}: {fee_link_err}",
									)
					except Exception as fee_err:
						frappe.log_error(
							"Bank Import CAMT.052 Error",
							f"Failed to create Bank Fee Payment Entry for {reference_no}: {fee_err}",
						)

		except Exception as err:
			frappe.log_error(
				"Bank Import CAMT.052",
				f"Failed to create Payment Entry for {txn.get('unique_reference')}: {err}",
			)

	# Create Process Payment Reconciliation documents for each collected party
	reconciliation_docs = []
	for (party_type, party), info in collected_parties.items():
		try:
			account = info["account"]
			if not account:
				frappe.log_error("Bank Import CAMT.052", f"No default {party_type} account found for {party}")
				continue

			ppr_doc = frappe.get_doc(
				{
					"doctype": "Process Payment Reconciliation",
					"company": company,
					"party_type": party_type,
					"party": party,
					"receivable_payable_account": account,
				}
			)
			ppr_doc.insert(ignore_permissions=True)
			reconciliation_docs.append(ppr_doc.name)
		except Exception as err:
			frappe.log_error(
				"Bank Import CAMT.052 Process Payment Reconciliation",
				f"Failed to create PPR for {party_type} {party}: {err}",
			)

	return {
		"message": _("Checked {1} bank transactions. Created {0} payment entries").format(
			len(created_entries), len(transactions)
		),
		"records": created_entries,
		"reconciliation_docs": reconciliation_docs,
	}


@frappe.whitelist()
def import_camt_statement(content, description=None, auto_submit=False):
	"""Wrapper for the page to import a CAMT XML statement.

	auto_submit flag controls whether created Payment Entries
	are submitted immediately or left in Draft state.
	"""

	errors = []
	created = []
	auto_submit_flag = False
	if str(auto_submit) in ("1", "true", "True"):
		auto_submit_flag = True

	try:
		result = read_camt054(content, account=None, auto_submit=auto_submit_flag)
		created = result.get("records", []) if isinstance(result, dict) else []
	except Exception as err:
		frappe.log_error("LT Bank Statement Import", str(err))
		errors.append(str(err))

	summary = _("Created {0} payment entries").format(len(created))
	if auto_submit_flag:
		summary = _("{0} (submitted)").format(summary)
	else:
		summary = _("{0} (saved as Drafts)").format(summary)

	return {
		"summary": summary,
		"records": created,
		"errors": errors,
	}


def make_payment_entry(
	amount,
	date,
	reference_no,
	paid_from=None,
	paid_to=None,
	type="Receive",
	party=None,
	party_type=None,
	references=None,
	remarks=None,
	auto_submit=False,
	exchange_rate=1,
	party_iban=None,
	company=None,
	pattern=None,
):
	if not company and paid_from:
		company = frappe.get_value("Account", paid_from, "company")
	elif not company and paid_to:
		company = frappe.get_value("Account", paid_to, "company")

	# Exchange rates
	company_currency = frappe.get_value("Company", company, "default_currency")
	if type == "Receive":
		account_currency = frappe.get_value("Account", paid_to, "account_currency")
	else:
		account_currency = frappe.get_value("Account", paid_from, "account_currency")
	if account_currency and account_currency != company_currency and exchange_rate == 1:
		# reevaluate exchange rate
		try:
			exchange_rate = get_exchange_rate(
				from_currency=account_currency, to_currency=company_currency, transaction_date=date
			)
		except Exception:
			# If exchange rate cannot be determined, keep default of 1
			pass

	base_payment_data = {
		"doctype": "Payment Entry",
		"paid_amount": float(amount),
		"received_amount": float(amount),
		"reference_no": reference_no,
		"reference_date": date,
		"posting_date": date,
		"remarks": remarks,
		"camt_amount": float(amount),
		"bank_account_no": party_iban,
		"company": company,
		"source_exchange_rate": exchange_rate,
		"target_exchange_rate": exchange_rate,
	}

	if type == "Receive":
		payment_specific_data = {
			"payment_type": "Receive",
			"party_type": party_type,
			"party": party,
			"paid_to": paid_to,
		}
	elif type == "Pay":
		payment_specific_data = {
			"payment_type": "Pay",
			"party_type": party_type,
			"party": party,
			"paid_from": paid_from,
		}
	else:
		payment_specific_data = {
			"payment_type": "Internal Transfer",
			"paid_from": paid_from,
			"paid_to": paid_to,
		}

	payment_entry = frappe.get_doc({**base_payment_data, **payment_specific_data})

	if party_type == "Employee":
		default_employee_payable_account = frappe.get_value(
			"Lithuania Compliance Settings",
			"Lithuania Compliance Settings",
			"default_employee_payable_account",
		)
		if default_employee_payable_account:
			payment_entry.paid_to = default_employee_payable_account

	new_entry = payment_entry.insert()

	# add references after insert (otherwise they are overwritten)
	if type == "Pay" and party_type == "Employee":
		# Use Expense Claim only if the DocType exists (HRMS installed)
		try:
			if frappe.db.exists("DocType", "Expense Claim"):
				reference_type = "Expense Claim"
			else:
				reference_type = None
		except Exception:
			reference_type = None
	elif type == "Pay":
		reference_type = "Purchase Invoice"
	else:
		reference_type = "Sales Invoice"

	if references and reference_type:
		for reference in ast.literal_eval(references):
			create_reference(new_entry.name, reference, reference_type)

	# automatically submit if enabled
	if auto_submit:
		matched_entry = frappe.get_doc("Payment Entry", new_entry.name)  # include changes from reference
		if matched_entry.difference_amount != 0:
			# for auto-submit, we need to clear this out to the exchange account
			exchange_account = frappe.get_cached_value(
				"Company", matched_entry.company, "exchange_gain_loss_account"
			)
			cost_center = frappe.get_cached_value("Company", matched_entry.company, "round_off_cost_center")
			matched_entry.append(
				"deductions",
				{
					"account": exchange_account,
					"cost_center": cost_center,
					"amount": matched_entry.difference_amount,
				},
			)
			matched_entry.save()
		matched_entry.submit()

	frappe.db.commit()
	return {"link": get_url_to_form("Payment Entry", new_entry.name), "payment_entry": new_entry.name}


# creates the reference record in a payment entry
def create_reference(payment_entry, invoice_reference, invoice_type="Sales Invoice"):
	reference_entry = frappe.get_doc({"doctype": "Payment Entry Reference"})
	reference_entry.parent = payment_entry
	reference_entry.parentfield = "references"
	reference_entry.parenttype = "Payment Entry"
	reference_entry.reference_doctype = invoice_type
	reference_entry.reference_name = invoice_reference
	if "Invoice" in invoice_type:
		reference_entry.total_amount = frappe.get_value(invoice_type, invoice_reference, "base_grand_total")
		reference_entry.outstanding_amount = frappe.get_value(
			invoice_type, invoice_reference, "outstanding_amount"
		)
		paid_amount = frappe.get_value("Payment Entry", payment_entry, "paid_amount")
		if paid_amount > reference_entry.outstanding_amount:
			reference_entry.allocated_amount = reference_entry.outstanding_amount
		else:
			reference_entry.allocated_amount = paid_amount
	else:  # expense claim
		reference_entry.total_amount = frappe.get_value(
			invoice_type, invoice_reference, "total_claimed_amount"
		)
		reference_entry.outstanding_amount = reference_entry.total_amount
		paid_amount = frappe.get_value("Payment Entry", payment_entry, "paid_amount")
		if paid_amount > reference_entry.outstanding_amount:
			reference_entry.allocated_amount = reference_entry.outstanding_amount
		else:
			reference_entry.allocated_amount = paid_amount
	reference_entry.insert()
	# update unallocated amount
	payment_record = frappe.get_doc("Payment Entry", payment_entry)
	payment_record.unallocated_amount -= reference_entry.allocated_amount
	payment_record.save()
	return


def get_numeric_only_reference(reference):
	filtered = ""
	for char in str(reference):
		if char.isdigit():
			filtered += char
	return filtered
