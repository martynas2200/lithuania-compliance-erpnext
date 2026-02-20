"""
API methods for Lithuania Compliance app
"""

import random
import re
import xml.etree.ElementTree as ET
from datetime import datetime

import frappe
from frappe import _
from werkzeug.wrappers import Response

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


def get_country_code(name):
	return frappe.db.get_value("Country", name, "code")


def get_default_vat_classificator():
	settings = frappe.get_doc(
		"Lithuania Compliance Settings", "Lithuania Compliance Settings", ignore_permissions=True
	)
	return settings.default_vat_classificator


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


def add_invoice_info(parent_element, invoice):
	"""
	Add invoice information XML elements to a parent element.

	Args:
	    parent_element: The parent XML element to add invoice info to
	    invoice: The invoice object with invoice_number, date, invoice_type, tax_lines
	"""
	ET.SubElement(parent_element, "InvoiceDate").text = invoice.date
	ET.SubElement(parent_element, "InvoiceType").text = invoice.invoice_type
	ET.SubElement(parent_element, "SpecialTaxation").text = ""
	# TODO: this should be an option to select in UI in the future
	ET.SubElement(parent_element, "References").text = ""
	ET.SubElement(parent_element, "VATPointDate").set("xsi:nil", "true")
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
		# ET.SubElement(document_total, "VATPointDate2").set("xsi:nil", "true")


@frappe.whitelist(allow_guest=False)
def get_isaf_totals(doc_name, doc_type):
	"""
	Returns a possible i.SAF export record to be displayed in the frontend for the user to inspect, applies to Sales Invoice, and Purchase Invoice
	"""
	if not doc_name or not doc_type or not (doc_type == "Sales Invoice" or doc_type == "Purchase Invoice"):
		return Response(status=400)

	doc = frappe.get_doc(doc_type, doc_name)

	return get_document_totals(doc.items, doc.taxes, doc.rounding_adjustment, get_default_vat_classificator())


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
		classifier = frappe.get_cached_doc("VAT Classificator", tax_code, ignore_permissions=True)
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


# TODO: Also a button to generate taxes based on classificators assigned to items would be useful. So a prompt are you sure, current list of taxes will be replaced etc. Or something else, so VAT classificators are used in sales properly.
def get_document_totals(items, taxes, rounding, default_tax_classificator):
	"""
	Calculate document totals for i.SAF export

	Args:
	    items: List of invoice items
	    taxes: List of tax entries
	    default_tax_classificator: Default VAT classificator to use if item does not have one
	Returns:
	    List of dicts with tax_code, tax_percentage, taxable_value, amount
	"""
	# go through all items, and group them by assigned or default vat classificator
	tax_summary = {}
	for item in items:
		# Check vat classificator on Invoice Item level first, then check Item doctype, and fallback to default
		tax_code = item.get("vat_classificator")
		if not tax_code:
			item_doc = frappe.get_cached_doc("Item", item.get("item_code"), ignore_permissions=True)
			tax_code = item_doc.vat_classificator or default_tax_classificator
		tax_summary[tax_code] = get_or_create_tax_summary(tax_summary, tax_code, item.get("item_code"))
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
			raise _(
				"Discrepancy found for tax code {0}: tax percentage is {1} but tax amount is 0. Please check your invoice items and taxes."
			).format(tax_code, summary["tax_percentage"])

	if rounding and rounding != 0.0:
		tax_summary["PVM100"] = get_or_create_tax_summary(tax_summary, "PVM100", "Rounding Adjustment")
		tax_summary["PVM100"]["taxable_value"] += rounding

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

	default_tax_classificator = get_default_vat_classificator()

	for doc_info in doc_mapping.get(export_type, []):
		doctype = doc_info["doctype"]
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
		for inv in invoice_list:
			# Fetch full document to access child tables (items, taxes)
			invoice_doc = frappe.get_doc(doctype, inv.name, ignore_permissions=True)
			# Filter by invoice type
			match = re.search(r"\b([A-Z]{2})\b", invoice_doc.get("invoice_type_lt", ""))
			invoice_type_code = match.group(1) if match else None
			if invoice_type_code not in types or inv.docstatus == 2:
				continue

			if inv.docstatus == 0:
				frappe.throw(
					_(
						"{0} {1} is a draft, however, it is set to be exported per invoice_type_lt selection {2}. Please submit the document or change the invoice_type_lt to exclude from the i.SAF report."
					).format(doctype, invoice_doc.get("name"), invoice_type_code)
				)
			party_name = invoice_doc.get("customer_name") or invoice_doc.get("supplier_name")
			if not party_name:
				# Skip invoices without a valid customer or supplier
				continue

			party_doc = frappe.get_doc(party, party_name, ignore_permissions=True)
			party_info = process_party_for_isaf(common_parties, party_doc)

			# Catching the error so we indicate which document has the problem
			try:
				tax_lines = get_document_totals(
					items=invoice_doc.items,
					taxes=invoice_doc.taxes,
					rounding=invoice_doc.rounding_adjustment,
					default_tax_classificator=default_tax_classificator,
				)
			except Exception as e:
				frappe.throw(
					_("Error processing {0} {1}: {2}").format(doctype, invoice_doc.get("name"), str(e))
				)
			bill_no = None
			if export_type == "received":
				bill_no = invoice_doc.get("bill_no")
				# NOTE: bill_date is not a part of Sales Invoice doctype, so might consider adding it via custom field if needed as we did with bill_no.
				if not invoice_doc.get("bill_date") and doctype == "Purchase Invoice":
					frappe.msgprint(
						_("{} {} does not have a bill date set. Using posting date instead.").format(
							doctype, invoice_doc.get("name")
						)
					)
			elif export_type == "issued":
				bill_no = invoice_doc.get("name")
			if not bill_no:
				frappe.throw(
					_(
						"{0} {1} does not have a valid bill number. Please set the bill number before exporting to i.SAF."
					).format(doctype, invoice_doc.get("name"))
				)

			invoices.append(
				frappe._dict(
					{
						"invoice_number": bill_no,
						"party": party_info,
						"date": (invoice_doc.bill_date or invoice_doc.posting_date).strftime("%Y-%m-%d"),
						"registration_account_date": invoice_doc.posting_date.strftime("%Y-%m-%d"),
						"invoice_type": invoice_type_code,
						"export_type": export_type,
						"tax_lines": tax_lines,
					}
				)
			)

	return common_parties, invoices


@frappe.whitelist(allow_guest=False)
def generate_isaf_xml(export_type, from_date, to_date):
	"""
	Generate i.SAF XML file for Lithuania tax compliance

	Args:
	    export_type: 'issued' or 'received' or 'both'
	    from_date: Start date for the period
	    to_date: End date for the period

	Returns:
	    dict with success status and file information
	"""
	print(export_type, from_date, to_date)
	xml_content = generate_isaf_xml_content(export_type, from_date, to_date)

	# Save file
	random_integer = random.randint(1000, 9999)
	date_str = datetime.strptime(from_date, "%Y-%m-%d").strftime("%Y_%m")
	filename = f"iSAF_{export_type}_{date_str}_{random_integer}.xml"
	# TODO: create a folder for all i.SAF exports
	file_doc = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": filename,
			"content": xml_content,
			"is_private": 1,
			"folder": "Home/Attachments",
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


def generate_isaf_xml_content(export_type, from_date, to_date):
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
		customers, sales = get_all_isaf_parties_and_invoices(export_type, from_date, to_date)
	if export_received:
		suppliers, purchases = get_all_isaf_parties_and_invoices(export_type, from_date, to_date)

	root = ET.Element("iSAFFile")
	root.set("xmlns", "http://www.vmi.lt/cms/imas/isaf")
	root.set("xmlns:xsi", "http://www.w3.org/2001/XMLSchema-instance")

	header = ET.SubElement(root, "Header")

	company = frappe.get_doc("Company", frappe.defaults.get_user_default("Company"))

	filedescription = ET.SubElement(header, "FileDescription")
	ET.SubElement(filedescription, "FileVersion").text = "iSAF1.2"
	# Use XSD-compliant dateTime: YYYY-MM-DDThh:mm:ssZ (UTC, no microseconds)
	ET.SubElement(filedescription, "FileDateCreated").text = (
		datetime.utcnow().replace(microsecond=0).isoformat()
	)
	ET.SubElement(filedescription, "DataType").text = (
		"F" if export_type == "both" else ("S" if export_issued else "P")
	)
	ET.SubElement(filedescription, "SoftwareCompanyName").text = "Frappe Technologies"
	ET.SubElement(filedescription, "SoftwareName").text = "ERPNext: Lithuania Compliance"
	ET.SubElement(filedescription, "SoftwareVersion").text = "0.0.1"
	# lithuania_compliance.__version__
	if company.business_code is None:
		frappe.throw(
			_(
				"Company {0} does not have a Business Code set. Please set it in the Company record before exporting to i.SAF."
			).format(company.name)
		)

	ET.SubElement(filedescription, "RegistrationNumber").text = company.business_code
	ET.SubElement(filedescription, "NumberOfParts").text = "1"
	# NOTE: there is no explicit requirement to split the data, so we might just have a massive single file
	ET.SubElement(filedescription, "PartNumber").text = (
		datetime.strptime(from_date, "%Y-%m-%d").strftime("%Y%m")
		+ "01"
		+ ("GI" if export_type == "both" else ("I" if export_issued else "G"))
	)
	selectioncriteria = ET.SubElement(filedescription, "SelectionCriteria")
	ET.SubElement(selectioncriteria, "SelectionStartDate").text = from_date
	ET.SubElement(selectioncriteria, "SelectionEndDate").text = to_date

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

			add_invoice_info(invoice_el, invoice)

	xml_str = ET.tostring(root, encoding="unicode", method="xml")
	return '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_str
