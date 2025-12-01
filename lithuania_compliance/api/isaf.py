"""
API methods for Lithuania Compliance app
"""

import json
import random
import xml.etree.ElementTree as ET
from datetime import datetime
from xml.dom import minidom

import frappe
from frappe import _


@frappe.whitelist()
def generate_isaf_xml(export_type, from_date, to_date, excluded_invoices=None):
	"""
	Generate i.SAF XML file for Lithuania tax compliance

	Args:
		export_type: 'receivable' or 'payable'
		from_date: Start date for the period
		to_date: End date for the period
		excluded_invoices: JSON string of invoice names to exclude

	Returns:
		dict with success status and file information
	"""
	try:
		if isinstance(excluded_invoices, str):
			excluded_invoices = json.loads(excluded_invoices)
		excluded_invoices = excluded_invoices or []

		# Determine doctype
		doctype = "Sales Invoice" if export_type == "receivable" else "Purchase Invoice"

		# Fetch invoices
		filters = {"posting_date": ["between", [from_date, to_date]], "docstatus": 1}

		if excluded_invoices:
			filters["name"] = ["not in", excluded_invoices]

		invoices = frappe.get_all(
			doctype,
			filters=filters,
			fields=[
				"name",
				"posting_date",
				"customer",
				"supplier",
				"customer_name",
				"supplier_name",
				"grand_total",
				"total_taxes_and_charges",
				"net_total",
				"currency",
				"tax_id",
				"customer_gstin",
				"supplier_gstin",
			],
		)

		# Generate XML
		xml_content = generate_isaf_xml_content(invoices, export_type, from_date, to_date)

		# Save file
		random_integer = random.randint(1000, 9999)
		date_str = datetime.strptime(from_date, "%Y-%m-%d").strftime("%Y_%m")
		filename = f"iSAF_{export_type}_{date_str}_{random_integer}.xml"
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
			"file_url": file_doc.file_url,
			"invoice_count": len(invoices),
		}

	except Exception as e:
		frappe.log_error(_("i.SAF XML Generation"), f"i.SAF Generation Error: {e!s}")
		return {"success": False, "error": str(e)}


def generate_isaf_xml_content(invoices, export_type, from_date, to_date):
	"""
	Generate the actual XML content for i.SAF format

	This is a placeholder implementation. You should customize this
	according to the official Lithuania i.SAF specification.
	"""

	# Create root element
	root = ET.Element("iSAF")
	root.set("xmlns", "urn:oecd:ties:isaf:v1.0")
	root.set("version", "1.0")

	# TODO: Implement according to i.SAF specification

	# Convert to pretty XML string
	xml_str = ET.tostring(root, encoding="unicode")
	dom = minidom.parseString(xml_str)
	pretty_xml = dom.toprettyxml(indent="  ")

	return pretty_xml
