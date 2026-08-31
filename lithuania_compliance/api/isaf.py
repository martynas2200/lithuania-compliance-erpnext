"""
API methods for Lithuania Compliance app
"""

import random
import re
import xml.etree.ElementTree as ET
from calendar import monthrange
from datetime import datetime, timezone

import frappe
from frappe import _
from frappe.core.api.file import create_new_folder
from frappe.utils.caching import request_cache
from werkzeug.wrappers import Response

import lithuania_compliance.settings as lt_settings

doc_mapping = {
	"received": [
		{
			"doctype": "Sales Invoice",
			"types": ["DS", "VD"],
		},
		{
			"doctype": "Purchase Invoice",
			"types": ["SF", "KS", "VS", "VK"],
		},
	],
	"issued": [
		{
			"doctype": "Sales Invoice",
			"types": ["SF", "KS", "VS", "VK"],
		},
		{
			"doctype": "Purchase Invoice",
			"types": ["DS", "VD"],
		},
	],
}

ISAF_EXPORTS_FOLDER_NAME = "iSAF Exports"
ISAF_EXPORTS_PARENT_FOLDER = "Home/Attachments"

CHILD_TABLE_MAPPING = {
	"Sales Invoice": {
		"items": "Sales Invoice Item",
		"taxes": "Sales Taxes and Charges",
		"item_wise_tax_details": "Item Wise Tax Detail",
	},
	"Purchase Invoice": {
		"items": "Purchase Invoice Item",
		"taxes": "Purchase Taxes and Charges",
		"item_wise_tax_details": "Item Wise Tax Detail",
	},
}


def get_or_create_isaf_exports_folder():
	existing = frappe.get_all(
		"File",
		filters={
			"file_name": ISAF_EXPORTS_FOLDER_NAME,
			"folder": ISAF_EXPORTS_PARENT_FOLDER,
			"is_folder": 1,
		},
		fields=["name"],
		limit=1,
	)
	if existing:
		return existing[0].name

	folder_doc = create_new_folder(ISAF_EXPORTS_FOLDER_NAME, ISAF_EXPORTS_PARENT_FOLDER)
	return folder_doc.name


@request_cache
def get_country_code(name):
	if not name:
		return None
	return frappe.db.get_value("Country", name, "code")


@request_cache
def get_vat_classificator(tax_code):
	if not tax_code:
		return None
	return frappe.get_cached_doc("VAT Classificator", tax_code, ignore_permissions=True)


@request_cache
def get_item_vat_classificator(item_code):
	"""Return the VAT classificator set on the Item doctype (item card)."""
	if not item_code:
		return None
	return frappe.get_cached_doc("Item", item_code, ignore_permissions=True).get("vat_classificator")


@request_cache
def get_party_doc(party_doctype, party_name):
	if not party_doctype or not party_name:
		return None
	return frappe.get_doc(party_doctype, party_name, ignore_permissions=True)


def process_party_for_isaf(common_parties, party_doc):
	"""
	Process party information for i.SAF export.

	Args:
	    common_parties: Dict to store unique parties by name
	    party_doc: Party document object

	Returns:
	    The party document object
	"""
	# Check if exists in common parties by unique name
	if party_doc.name not in common_parties:
		# enumerate based on how many parties are already there
		party_doc.id = str(len(common_parties) + 1)
		common_parties[party_doc.name] = party_doc
	return common_parties[party_doc.name]


def add_party_info(parent_element, party, is_customer=True):
	"""
	Add customer information XML elements to a parent element.

	Args:
	    parent_element: The parent XML element to add customer info to
	    customer: The customer/party object with id, vat_number, registration_number, country_code, name
	"""
	if is_customer:
		ET.SubElement(parent_element, "CustomerID").text = party.id
	else:
		ET.SubElement(parent_element, "SupplierID").text = party.id
	ET.SubElement(parent_element, "VATRegistrationNumber").text = party.tax_id or "ND"
	ET.SubElement(parent_element, "RegistrationNumber").text = party.business_code or "ND"
	# TODO: future: should a personal code be used if the supplier a farmer
	ET.SubElement(parent_element, "Country").text = (get_country_code(party.country) or "ND").upper()
	ET.SubElement(parent_element, "Name").text = party.name


def add_invoice_info(parent_element, invoice, purchase_invoice=False):
	"""
	Add invoice information XML elements to a parent element.

	Args:
	    parent_element: The parent XML element to add invoice info to
	    invoice: The invoice object with invoice_number, date, invoice_type, tax_lines
	    purchase_invoice: Whether to include the RegistrationAccountDate
	        element. Per the i.SAF spec it is only defined on PurchaseInvoice, so this should
	        only be True for purchase invoices.
	"""
	ET.SubElement(parent_element, "InvoiceDate").text = invoice.date
	ET.SubElement(parent_element, "InvoiceType").text = invoice.invoice_type
	ET.SubElement(parent_element, "SpecialTaxation").text = ""
	# TODO: this should be an option to select in UI in the future
	ET.SubElement(parent_element, "References").text = ""
	ET.SubElement(parent_element, "VATPointDate").set("xsi:nil", "true")
	# RegistrationAccountDate is only defined on PurchaseInvoice in the i.SAF schema, not SalesInvoice
	if purchase_invoice:
		ET.SubElement(parent_element, "RegistrationAccountDate").text = invoice.registration_account_date
	document_totals = ET.SubElement(parent_element, "DocumentTotals")
	for line in invoice.tax_lines:
		document_total = ET.SubElement(document_totals, "DocumentTotal")
		ET.SubElement(document_total, "TaxableValue").text = str(round(line["taxable_value"], 2))
		ET.SubElement(document_total, "TaxCode").text = line["tax_code"]

		if line["tax_percentage"] is not None:
			ET.SubElement(document_total, "TaxPercentage").text = str(round(line["tax_percentage"], 2))
		else:
			# The VAT rate expressed in per cent. This element may be not filled in (empty element) if no VAT rate is applicable according to the VAT classification (e.g. the supplies shall be exempt from VAT). If the VAT rate is equal to 0%, the value 0 shall be indicated.
			ET.SubElement(document_total, "TaxPercentage").set("xsi:nil", "true")

		if line["amount"] is not None and line["amount"] != 0.0:
			ET.SubElement(document_total, "Amount").text = str(round(line["amount"], 2))
		else:
			ET.SubElement(document_total, "Amount").set("xsi:nil", "true")

		if not purchase_invoice:
			ET.SubElement(document_total, "VATPointDate2").set("xsi:nil", "true")


def _get_vat_account(doc_type):
	return (
		lt_settings.get_sales_vat_account()
		if doc_type == "Sales Invoice"
		else lt_settings.get_purchase_vat_account()
	)


@frappe.whitelist(allow_guest=False)
def get_isaf_totals(doc_name, doc_type):
	"""
	Returns a possible i.SAF export record to be displayed in the frontend for the user to inspect, applies to Sales Invoice, and Purchase Invoice
	"""
	if not doc_name or not doc_type or not (doc_type == "Sales Invoice" or doc_type == "Purchase Invoice"):
		return Response(status=400)

	doc = frappe.get_doc(doc_type, doc_name)

	return get_document_totals(
		doc.items,
		doc.taxes,
		doc.rounding_adjustment,
		item_wise_tax_details=doc.get("item_wise_tax_details"),
		vat_account=_get_vat_account(doc_type),
	)


def get_or_create_tax_summary(tax_summary, tax_code, item_code):
	"""
	Helper function to get or create a tax summary entry for a given tax code.

	Args:
	    tax_summary: Dict to store tax summaries
	    tax_code: The VAT classificator code
	    item_code: The item code for error messaging

	Returns:
	    The tax summary dict for the tax_code
	"""
	if tax_code not in tax_summary:
		classifier = get_vat_classificator(tax_code)
		if classifier is None:
			frappe.throw(
				_(
					"Strange! No VAT Classificator found with code {0}. It should exist as it is assigned to an item {1}."
				).format(tax_code, item_code)
			)
		tax_summary[tax_code] = {
			"tax_code": tax_code,
			"taxable_value": 0.0,
			"amount": 0.0,
			"tax_percentage": classifier.rate if classifier and not classifier.is_exempt else None,
		}
	return tax_summary[tax_code]


# NOTE: No function for tax generation for sale invoices based off the items for now, as Item Tax Template with Sale Taxes and Charges Template does it all automatically.
def get_document_totals(
	items,
	taxes,
	rounding,
	item_wise_tax_details=None,
	vat_account=None,
):
	"""
	Calculate document totals for i.SAF export.

	Supports two ways VAT taxes can be set up on an invoice:

	1. Explicit ``Actual`` tax rows, each carrying its own ``vat_classificator``
	2. Native automatic tax rows (``On Net Total``, ``On Previous Row``, etc.) where VAT is computed automatically and accumulated into a single account row. In this case the per-item breakdown from ``item_wise_tax_details`` is used.

	Args:
	    items: List of invoice items
	    taxes: List of tax entries
	    rounding: Rounding adjustment amount
	    default_tax_classificator: Default VAT classificator to use if item does not have one
	    item_wise_tax_details: Optional list of Item Wise Tax Detail rows
	    vat_account: Optional default output/input VAT account used to recognise the automatic VAT tax row(s) in the native flow
	Returns:
	    List of dicts with tax_code, tax_percentage, taxable_value, amount
	"""
	default_tax_classificator = lt_settings.get_default_vat_classificator()
	automatic_tax_rows = [
		tax
		for tax in taxes
		if tax.get("charge_type")
		and tax.get("charge_type") != "Actual"
		and (not vat_account or tax.get("account_head") == vat_account)
	]
	automatic_tax_names = {tax.get("name") for tax in automatic_tax_rows}

	tax_summary = {}
	if automatic_tax_names and item_wise_tax_details:
		item_by_name = {item.get("name"): item for item in items if item.get("name")}
		counted_taxable_items = set()
		for detail in item_wise_tax_details:
			# Only attribute amounts from the automatic VAT tax row(s)
			if detail.get("tax_row") not in automatic_tax_names:
				continue
			# TODO: might be a good idea to introduce a checkbox or a list of accounts for vat instead of two options.
			item = item_by_name.get(detail.get("item_row")) or {}
			tax_code = (
				item.get("vat_classificator")
				or get_item_vat_classificator(item.get("item_code"))
				or default_tax_classificator
			)
			summary = get_or_create_tax_summary(
				tax_summary,
				tax_code,
				item.get("item_code"),
			)
			if detail.get("item_row") not in counted_taxable_items:
				# Conditional might be an overkill as it should be just a single tax row that does the automatic calculation.
				summary["taxable_value"] += detail.get("taxable_amount", 0.0)
				counted_taxable_items.add(detail.get("item_row"))
			summary["amount"] += detail.get("amount", 0.0)
	else:
		# go through all items, and group them by assigned or default vat classificator
		for item in items:
			# Check vat classificator on Invoice Item level first, then check Item doctype, and fallback to default
			tax_code = (
				item.get("vat_classificator")
				or get_item_vat_classificator(item.get("item_code"))
				or default_tax_classificator
			)
			tax_summary[tax_code] = get_or_create_tax_summary(
				tax_summary,
				tax_code,
				item.get("item_code"),
			)
			tax_summary[tax_code]["taxable_value"] += item.get("base_amount", 0.0)

		for tax in taxes:
			tax_code = tax.get("vat_classificator") or default_tax_classificator
			tax_amount = tax.get("tax_amount", 0.0)
			if tax_code not in tax_summary:
				frappe.throw(
					_(
						"Tax entry found for tax code {0} but no items assigned to it. Please check your invoice items and taxes."
					).format(tax_code)
				)
			tax_summary[tax_code]["amount"] += tax_amount

	# check if we have discrepancies due to rounding etc.
	for tax_code, summary in tax_summary.items():
		summary["taxable_value"] = round(summary["taxable_value"], 2)
		summary["amount"] = round(summary["amount"], 2)
		# check if there is rate > 0, but amount is 0, or vice versa
		if (
			summary["tax_percentage"] is not None
			and summary["amount"] == 0.0
			and summary["tax_percentage"] > 0
		):
			frappe.throw(
				_(
					"Discrepancy found for tax code {0}: tax percentage is {1} but tax amount is 0. Please check your invoice items and taxes.<br><br>Tip: This usually means the VAT for this tax code is unknown. Common causes:<br>• The VAT tax row uses the <b>Actual</b> charge type but has no <b>VAT Classificator</b> set — each <b>Actual</b> tax row must have a VAT Classificator assigned.<br>• The tax rate on the item or its Item Tax Template does not match the VAT Classificator rate, so the computed amount is 0.<br>If you want VAT to be calculated automatically, switch the tax row to <b>On Net Total</b> so it is computed from the Item Taxes and the Sales/Purchase Taxes and Charges Template."
				).format(tax_code, summary["tax_percentage"])
			)
		# Check that the actual tax amount matches the expected tax rate.
		if summary["tax_percentage"] is not None and summary["taxable_value"] != 0:
			actual_tax_percentage = (summary["amount"] / summary["taxable_value"]) * 100

			if abs(actual_tax_percentage - summary["tax_percentage"]) > 1:
				frappe.throw(
					_(
						"Discrepancy found for tax code {0}: the VAT Classificator rate is {1}%, but the VAT on this invoice works out to {2}%. This usually means the tax rows were entered manually with the <b>Actual</b> charge type and don't match the VAT Classificator rate.<br><br>Tip: Switch the tax row(s) to <b>On Net Total</b> so the VAT is computed automatically from the Item Taxes and the Sales/Purchase Taxes and Charges Template."
					).format(
						tax_code,
						summary["tax_percentage"],
						round(actual_tax_percentage, 2),
					)
				)
	# NOTE: accountant pointed out when there is rounding down, we SHOULD NOT create a negative DocumentTotal row of PVM100, but appearently we should decrease the main classificator taxable amount instead.
	if rounding and (rounding > 0.0 or (rounding < 0.0 and "PVM100" in tax_summary)):
		tax_summary["PVM100"] = get_or_create_tax_summary(
			tax_summary,
			"PVM100",
			"Rounding Adjustment",
		)
		tax_summary["PVM100"]["taxable_value"] += rounding
	elif rounding and rounding < 0.0 and "PVM100" not in tax_summary and "PVM1" in tax_summary:
		tax_summary["PVM1"]["taxable_value"] += rounding

	return list(tax_summary.values())


def get_all_isaf_parties_and_invoices(export_type, from_date, to_date):
	"""
	Fetch all invoices for i.SAF export

	Args:
	    export_type: 'issued' or 'received'
	    from_date: Start date for the period
	    to_date: End date for the period

	Returns:
	    List of invoice dicts and dict of common parties
	"""
	common_parties = {}
	invoices = []

	for doc_info in doc_mapping.get(export_type, []):
		doctype = doc_info["doctype"]
		child_tables = CHILD_TABLE_MAPPING.get(doctype)
		if not child_tables:
			continue
		party = "Customer" if doctype == "Sales Invoice" else "Supplier"
		types = doc_info["types"]
		fields = [
			"name",
			party,
			"posting_date",
			"invoice_type_lt",
			"company",
			"docstatus",
			"rounding_adjustment",
		]
		if party == "Customer":
			fields.extend(["customer_name", "customer_group"])
		else:
			fields.extend(["supplier_name", "bill_no", "bill_date"])
		# TODO: not urgent: we need to use bill_date, but not always it is set, and in our case, we always set both dates the same, but if the company got scricter rules when it comes to auditing, revisit this
		invoice_list = frappe.get_all(
			doctype,
			filters={
				"posting_date": ["between", [from_date, to_date]],
			},
			fields=fields,
			ignore_permissions=True,
			order_by="posting_date",
		)

		if not invoice_list:
			continue

		invoice_names = [inv.name for inv in invoice_list]

		items = frappe.get_all(
			child_tables["items"],
			filters={"parent": ["in", invoice_names]},
			fields=["name", "parent", "item_code", "vat_classificator", "base_amount"],
			ignore_permissions=True,
			limit_page_length=0,
		)
		taxes = frappe.get_all(
			child_tables["taxes"],
			filters={"parent": ["in", invoice_names]},
			fields=["name", "parent", "vat_classificator", "tax_amount", "charge_type", "account_head"],
			ignore_permissions=True,
			limit_page_length=0,
		)
		item_wise_tax_details = frappe.get_all(
			child_tables["item_wise_tax_details"],
			filters={"parent": ["in", invoice_names]},
			fields=["parent", "item_row", "tax_row", "rate", "amount", "taxable_amount"],
			ignore_permissions=True,
			limit_page_length=0,
		)

		items_by_invoice = {}
		for row in items:
			items_by_invoice.setdefault(row.parent, []).append(row)

		taxes_by_invoice = {}
		for row in taxes:
			taxes_by_invoice.setdefault(row.parent, []).append(row)

		item_wise_tax_details_by_invoice = {}
		for row in item_wise_tax_details:
			item_wise_tax_details_by_invoice.setdefault(row.parent, []).append(row)

		for inv in invoice_list:
			# Filter by invoice type
			match = re.search(r"\b([A-Z]{2})\b", inv.get("invoice_type_lt", ""))
			invoice_type_code = match.group(1) if match else None
			if invoice_type_code not in types or inv.docstatus == 2:
				continue

			if inv.docstatus == 0:
				frappe.throw(
					_(
						"{0} {1} is a draft, however, it is set to be exported per invoice_type_lt selection {2}. Please submit the document or change the invoice_type_lt to exclude from the i.SAF report."
					).format(doctype, inv.get("name"), invoice_type_code)
				)
			party_name = inv.get("customer_name") or inv.get("supplier_name")
			if not party_name:
				# Skip invoices without a valid customer or supplier
				continue

			party_doc = get_party_doc(party, party_name)
			party_info = process_party_for_isaf(common_parties, party_doc)

			# Catching the error so we indicate which document has the problem
			try:
				tax_lines = get_document_totals(
					items=items_by_invoice.get(inv.name, []),
					taxes=taxes_by_invoice.get(inv.name, []),
					rounding=inv.rounding_adjustment,
					item_wise_tax_details=item_wise_tax_details_by_invoice.get(inv.name, []),
					vat_account=_get_vat_account(doctype),
				)
			except Exception as e:
				frappe.throw(_("Error processing {0} {1}: {2}").format(doctype, inv.get("name"), str(e)))
			bill_no = None
			if export_type == "received":
				bill_no = inv.get("bill_no")
				# NOTE: bill_date is not a part of Sales Invoice doctype, so might consider adding it via custom field if needed as we did with bill_no.
				if not inv.get("bill_date") and doctype == "Purchase Invoice":
					frappe.msgprint(
						_("{} {} does not have a bill date set. Using posting date instead.").format(
							doctype, inv.get("name")
						)
					)
			elif export_type == "issued":
				bill_no = inv.get("name")
			if not bill_no:
				frappe.throw(
					_(
						"{0} {1} does not have a valid bill number. Please set the bill number before exporting to i.SAF."
					).format(doctype, inv.get("name"))
				)

			invoices.append(
				frappe._dict(
					{
						"invoice_number": bill_no,
						"party": party_info,
						"date": (inv.bill_date or inv.posting_date).strftime("%Y-%m-%d"),
						"registration_account_date": inv.posting_date.strftime("%Y-%m-%d"),
						"invoice_type": invoice_type_code,
						"export_type": export_type,
						"tax_lines": tax_lines,
					}
				)
			)

	return common_parties, invoices


@frappe.whitelist(allow_guest=False)
def generate_isaf_xml(export_type, year, month, company):
	"""
	Generate i.SAF XML file for Lithuania tax compliance

	Args:
	    company: Company name
	    export_type: 'issued' or 'received' or 'both'
	    year: Year integer
	    month: Month english string

	Returns:
	    dict with success status and file information
	"""
	year = int(year)
	month_number = datetime.strptime(month, "%B").month

	from_date = datetime(year, month_number, 1).strftime("%Y-%m-%d")
	to_date = datetime(year, month_number, monthrange(year, month_number)[1]).strftime("%Y-%m-%d")

	xml_content = generate_isaf_xml_content(export_type, from_date, to_date, company)

	# Save file
	random_integer = random.randint(1000, 9999)
	date_str = datetime.strptime(from_date, "%Y-%m-%d").strftime("%Y_%m")
	filename = f"iSAF_{export_type}_{date_str}_{random_integer}.xml"
	folder = get_or_create_isaf_exports_folder()
	file_doc = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": filename,
			"content": xml_content,
			"is_private": 1,
			"folder": folder,
		}
	)
	file_doc.save()
	frappe.db.commit()

	return {
		"success": True,
		"file_name": filename,
		"total_invoices": len(re.findall(r"<Invoice>", xml_content)),
		"file_url": file_doc.file_url,
	}


def generate_isaf_xml_content(export_type, from_date, to_date, company):
	"""
	Generate the actual XML content for i.SAF format

	This is a placeholder implementation. You should customize this
	according to the official Lithuania i.SAF specification.
	"""
	export_issued = export_type == "issued" or export_type == "both"
	export_received = export_type == "received" or export_type == "both"
	if not export_issued and not export_received:
		frappe.throw(_("Invalid export type. Must be 'issued', 'received' or 'both'."))

	if export_issued:
		customers, sales = get_all_isaf_parties_and_invoices("issued", from_date, to_date)
	if export_received:
		suppliers, purchases = get_all_isaf_parties_and_invoices("received", from_date, to_date)

	root = ET.Element("iSAFFile")
	root.set("xmlns", "http://www.vmi.lt/cms/imas/isaf")
	root.set("xmlns:xsi", "http://www.w3.org/2001/XMLSchema-instance")

	header = ET.SubElement(root, "Header")

	company = frappe.get_doc(
		"Company", company or frappe.get_cached_value("Global Defaults", "Global Defaults", "default_company")
	)

	file_description = ET.SubElement(header, "FileDescription")
	ET.SubElement(file_description, "FileVersion").text = "iSAF1.2"
	# Use XSD-compliant dateTime: YYYY-MM-DDThh:mm:ssZ (UTC, no microseconds)
	ET.SubElement(file_description, "FileDateCreated").text = (
		datetime.now(timezone.utc).replace(microsecond=0).isoformat()
	)
	ET.SubElement(file_description, "DataType").text = (
		"F" if export_type == "both" else ("S" if export_issued else "P")
	)
	ET.SubElement(file_description, "SoftwareCompanyName").text = "Frappe Technologies"
	ET.SubElement(file_description, "SoftwareName").text = "ERPNext: Lithuania Compliance"
	ET.SubElement(file_description, "SoftwareVersion").text = "0.0.3"
	# lithuania_compliance.__version__
	if company.business_code is None:
		frappe.throw(
			_(
				"Company {0} does not have a Business Code set. Please set it in the Company record before exporting to i.SAF."
			).format(company.name)
		)

	ET.SubElement(file_description, "RegistrationNumber").text = company.business_code
	ET.SubElement(file_description, "NumberOfParts").text = "1"
	# NOTE: there is no explicit requirement to split the data, so we might just have a massive single file
	ET.SubElement(file_description, "PartNumber").text = (
		datetime.strptime(from_date, "%Y-%m-%d").strftime("%Y%m")
		+ "01"
		+ ("GI" if export_type == "both" else ("I" if export_issued else "G"))
	)
	selection_criteria = ET.SubElement(file_description, "SelectionCriteria")
	ET.SubElement(selection_criteria, "SelectionStartDate").text = from_date
	ET.SubElement(selection_criteria, "SelectionEndDate").text = to_date

	# TODO: think how to validate the file afterwards, e.g. required fields, check if any tag is empty etc.
	master_files = ET.SubElement(root, "MasterFiles")
	source_documents = ET.SubElement(root, "SourceDocuments")
	if export_issued:
		customers_el = ET.SubElement(master_files, "Customers")
		for party in customers.values():
			customer = ET.SubElement(customers_el, "Customer")
			add_party_info(customer, party, is_customer=True)
		sales_invoices = ET.SubElement(source_documents, "SalesInvoices")
		for invoice in sales:
			invoice_el = ET.SubElement(sales_invoices, "Invoice")
			ET.SubElement(invoice_el, "InvoiceNo").text = invoice.invoice_number

			customer_info = ET.SubElement(invoice_el, "CustomerInfo")
			add_party_info(customer_info, invoice.party, is_customer=True)

			add_invoice_info(invoice_el, invoice)

	if export_received:
		suppliers_el = ET.SubElement(master_files, "Suppliers")
		for party in suppliers.values():
			supplier = ET.SubElement(suppliers_el, "Supplier")
			add_party_info(supplier, party, is_customer=False)
		purchase_invoices = ET.SubElement(source_documents, "PurchaseInvoices")
		for invoice in purchases:
			invoice_el = ET.SubElement(purchase_invoices, "Invoice")
			ET.SubElement(invoice_el, "InvoiceNo").text = invoice.invoice_number

			supplier_info = ET.SubElement(invoice_el, "SupplierInfo")
			add_party_info(supplier_info, invoice.party, is_customer=False)

			add_invoice_info(invoice_el, invoice, purchase_invoice=True)

	xml_str = ET.tostring(root, encoding="unicode", method="xml")
	return '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_str
