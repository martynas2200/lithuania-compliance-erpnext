"""Helpers and API for Purchase Invoice."""

from datetime import datetime

import frappe


def _add_supplier_for_items(doc):
	"""
	Ensure invoice supplier is in each Item's supplier list.

	For every item row in the Purchase Invoice, this job loads the
	corresponding Item and, if the invoice supplier is not already
	listed in the Item's ``supplier_items`` child table, appends a new
	row and saves the Item.
	"""
	supplier = getattr(doc, "supplier", None)
	if not supplier:
		return

	processed_items = set()

	for item in getattr(doc, "items", []) or []:
		item_code = getattr(item, "item_code", None)
		if not item_code or item_code in processed_items:
			continue

		processed_items.add(item_code)

		try:
			item_doc = frappe.get_doc("Item", item_code)
		except frappe.DoesNotExistError:
			# If the item no longer exists, just skip it
			continue

		existing_suppliers = {
			row.supplier
			for row in (getattr(item_doc, "supplier_items", []) or [])
			if getattr(row, "supplier", None)
		}

		if supplier not in existing_suppliers:
			item_doc.append("supplier_items", {"supplier": supplier})
			item_doc.save(ignore_permissions=True)
			frappe.db.commit()


def enqueue_supplier_items_sync(doc, method=None):
	"""Enqueue background job to validate suppliers on submit.

	Hook signature: ``doc, method``.
	"""
	frappe.enqueue(
		"lithuania_compliance.api.purchase_invoice._add_supplier_for_items",
		doc=doc,
		queue="short",
		now=False,
	)


@frappe.whitelist()
def get_item_prices(invoice_name):
	"""
	Get prices for all items in a Purchase Invoice.

	Logic for determining applicable price when multiple are valid:
	1. Filter prices where today's date falls between valid_from and valid_upto
	2. If multiple prices are applicable, select the one with the latest valid_from date
	   (newer price overrides older price)
	3. Return both applicable price and other valid prices for reference

	Args:
	    invoice_name: Name of the Purchase Invoice

	Returns:
	    List of dicts with item info and applicable prices
	"""
	invoice = frappe.get_doc("Purchase Invoice", invoice_name)
	today = frappe.utils.getdate(frappe.utils.now())

	items_data = []

	Item = frappe.qb.DocType("Item")
	ItemBarcode = frappe.qb.DocType("Item Barcode")
	VATClasificator = frappe.qb.DocType("VAT Classificator")

	# Expand invoice items with barcode info
	invoice_items_with_barcodes = (
		frappe.qb.from_(Item)
		.left_join(ItemBarcode)
		.on(Item.item_code == ItemBarcode.parent)
		.left_join(VATClasificator)
		.on(Item.vat_classificator == VATClasificator.name)
		.select(
			Item.item_code,
			Item.item_name,
			ItemBarcode.barcode,
			VATClasificator.rate.as_("vat_rate"),
		)
		.where(Item.item_code.isin([item.item_code for item in invoice.items]))
	).run(as_dict=True)

	# get default VAT classificator rate
	default_vat_classificator = frappe.get_single("Lithuania Compliance Settings").default_vat_classificator
	default_vat_rate = frappe.get_value("VAT Classificator", default_vat_classificator, "rate") or 21
	# Create lookup for query results by item_code
	item_lookup = {item["item_code"]: item for item in invoice_items_with_barcodes}

	# TODO: use clasificators of invoice items when available
	# Iterate through invoice items to preserve order and handle duplicates
	for invoice_item in invoice.items:
		item_code = invoice_item.item_code
		item_rate = invoice_item.rate

		# Get the corresponding query result
		item = item_lookup.get(item_code)
		if not item:
			continue

		prices = frappe.get_list(
			"Item Price",
			filters={
				"item_code": item_code,
				"selling": 1,
			},
			fields=["name", "price_list_rate", "currency", "valid_from", "valid_upto", "price_list"],
			order_by="valid_from desc",  # Newest first
		)

		applicable_price = None
		other_valid_prices = []

		for price in prices:
			valid_from = price.get("valid_from")
			valid_upto = price.get("valid_upto")

			# Check if price is currently valid
			is_valid = True

			if valid_from:
				valid_from_date = frappe.utils.getdate(valid_from)
				if today < valid_from_date:
					is_valid = False

			if valid_upto:
				valid_upto_date = frappe.utils.getdate(valid_upto)
				if today > valid_upto_date:
					is_valid = False

			if is_valid:
				if not applicable_price:
					applicable_price = price
				else:
					other_valid_prices.append(price)
			else:
				other_valid_prices.append(price)

		item.vat_rate = default_vat_rate if item.get("vat_rate") is None else item.get("vat_rate")
		# Calculate markup if applicable price exists
		markup = 0
		if applicable_price and item_rate:
			applicable_rate = applicable_price.get("price_list_rate", 0)
			if item_rate > 0:
				# Adding 21% VAT to the base price
				# TODO: Add a setting for VAT rate or if we plan to use clasificators for each item.
				cost_with_vat = item_rate * (1 + item.vat_rate / 100)
				markup = ((applicable_rate - cost_with_vat) / cost_with_vat) * 100

		items_data.append(
			{
				"item_code": item_code,
				"item_name": item.item_name,
				"vat_rate": item.vat_rate,
				"barcode": item.barcode,
				"rate": item_rate,
				"markup": round(markup, 2),
				"applicable_price": applicable_price,
				"other_valid_prices": other_valid_prices,
			}
		)

	return items_data
