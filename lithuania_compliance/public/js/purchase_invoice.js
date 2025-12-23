frappe.ui.form.on("Purchase Invoice", {
	refresh: function (frm) {
		if (!frm.is_new() && frm.doc.docstatus === 0) {
			frm.add_custom_button(
				__("Item Prices"),
				function () {
					getItemPricesAndOpenDialog(frm);
				},
				__("Preview")
			);
		} else if (!frm.is_new()) {
			frm.add_custom_button(
				__("Item Prices"),
				function () {
					getItemPricesAndOpenDialog(frm);
				},
				__("View")
			);
		}
	},
});

function getItemPricesAndOpenDialog(frm) {
	// Close all open dialogs
	$(".modal").modal("hide");
	$('.frappe-control[data-fieldtype="Dialog"]').remove();
	if (cur_dialog) {
		cur_dialog.hide();
	}

	frappe.call({
		method: "lithuania_compliance.api.purchase_invoice.get_item_prices",
		args: {
			invoice_name: frm.doc.name,
		},
		callback: function (r) {
			if (r.message) {
				show_manage_prices_dialog(frm, r.message);
			}
		},
	});
}

function get_markup_percentage(selling_price, buying_price) {
	if (!buying_price) return 0;
	const cost_with_vat = buying_price * 1.21; // 21% VAT
	return ((selling_price - cost_with_vat) / cost_with_vat) * 100;
}

function get_price_background_color(markup_percent) {
	return "#f5f5f5"; // Light gray
}

function show_manage_prices_dialog(frm, items_data) {
	let dialog = new frappe.ui.Dialog({
		title: __("Manage Item Prices"),
		fields: [{ fieldtype: "HTML", fieldname: "prices_html" }],
		primary_action_label: __("Close"),
		primary_action() {
			dialog.hide();
		},
		size: "large",
	});

	let html = '<div class="manage-prices-container">';
	html += `<table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
		<thead>
			<tr style="background: #f5f5f5; border-bottom: 2px solid #ddd;">
				<th style="padding: 10px; text-align: left; border: 1px solid #ddd;">${__("Item Code")} / ${__(
		"Name"
	)}</th>
				<th style="padding: 10px; text-align: left; border: 1px solid #ddd;">${__("Selling Price")} / ${__(
		"Valid"
	)}</th>
				<th style="padding: 10px; text-align: left; border: 1px solid #ddd;">${__("Markup")}</th>
				<th style="padding: 10px; text-align: left; border: 1px solid #ddd;">${__("Buying Price")}</th>
				<th style="padding: 10px; text-align: center; border: 1px solid #ddd;">${__("Actions")}</th>
			</tr>
		</thead>
		<tbody>`;

	for (let item of items_data) {
		const has_multiple = (item.other_valid_prices?.length || 0) > 0;
		const asterisk = has_multiple
			? ' <span style="color: #e74c3c; font-weight: bold;">*</span>'
			: "";

		if (item.applicable_price) {
			const price = item.applicable_price;
			const formatted_rate = frappe.format(price.price_list_rate, { fieldtype: "Currency" });
			const valid_until = price.valid_upto
				? " " + frappe.datetime.str_to_user(price.valid_upto)
				: "";

			html += `<tr style="border-bottom: 1px solid #ddd; background: #f0f8ff;">
				<td style="padding: 10px; border: 1px solid #ddd;">
					<a href="#" class="item-code-link" data-item-code="${
						item.item_code
					}" style="color: #0066cc; text-decoration: none; font-weight: bold;">
						${item.item_code}${asterisk}
					</a>
					<div style="font-size: 0.9em; color: #666; margin-top: 2px;">${item.item_name}</div>
				</td>
				<td style="padding: 10px; border: 1px solid #ddd;">${formatted_rate}
					<div style="font-size: 0.9em; color: #666; margin-top: 2px;text-align: right;">${frappe.datetime.str_to_user(
						price.valid_from
					)}${valid_until}</div>
				</td>
				<td style="padding: 10px; border: 1px solid #ddd;">${item.markup || " - - "} %</td>
				<td style="padding: 10px; border: 1px solid #ddd;">${item.rate}</td>
				<td style="padding: 10px; border: 1px solid #ddd; text-align: center;">
					<a href="#" class="btn btn-sm btn-default add-price-btn" data-item-code="${
						item.item_code
					}" style="color: #27ae60; text-decoration: none; padding: 5px 8px;" title="Add Price">
						<i class="fa fa-plus"></i>
					</a>
					<a href="#" class="btn btn-sm btn-default edit-price-btn" data-price-id="${
						price.name
					}" style="color: #0066cc; text-decoration: none; margin: 0 5px; padding: 5px 8px;" title="Edit">
						<i class="fa fa-pencil"></i>
					</a>
					<a href="#" class="btn btn-sm btn-default delete-price-btn" data-price-id="${
						price.name
					}" style="color: #e74c3c; text-decoration: none; margin: 0 5px; padding: 5px 8px;" title="Delete">
						<i class="fa fa-trash"></i>
					</a>
				</td>
			</tr>`;
		} else {
			html += `<tr style="border-bottom: 1px solid #ddd;">
				<td style="padding: 10px; border: 1px solid #ddd;">
					<a href="#" class="item-code-link" data-item-code="${
						item.item_code
					}" style="color: #0066cc; text-decoration: none; font-weight: bold;">
						${item.item_code}${asterisk}
					</a>
					<div style="font-size: 0.9em; color: #666; margin-top: 2px;">${item.item_name}</div>
				</td>
				<td colspan="3" style="padding: 10px; border: 1px solid #ddd; color: #666; font-style: italic;">${__(
					"No applicable price found"
				)}</td>
				<td style="padding: 10px; border: 1px solid #ddd; text-align: center;">
					<a href="#" class="btn btn-sm btn-default add-price-btn" data-item-code="${
						item.item_code
					}" style="color: #27ae60; text-decoration: none; padding: 5px 8px;" title="Add Price">
						<i class="fa fa-plus"></i>
					</a>
				</td>
			</tr>`;
		}
	}

	html += `	</tbody>
	</table>`;
	html += `<div style="margin-top: 20px;"><strong style="color: #e74c3c;">*</strong> ${__(
		"Indicates item has multiple prices"
	)}</div>`;
	html += "</div>";
	dialog.fields_dict.prices_html.$wrapper.html(html);

	// Attach event handlers after HTML is rendered
	dialog.$wrapper.on("click", ".item-code-link", function (e) {
		e.preventDefault();
		const item_code = $(this).data("item-code");
		frappe.set_route("Form", "Item", item_code);
	});

	dialog.$wrapper.on("click", ".edit-price-btn", function () {
		const price_id = $(this).data("price-id");
		frappe.set_route("Form", "Item Price", price_id);
	});

	dialog.$wrapper.on("click", ".delete-price-btn", function () {
		const price_id = $(this).data("price-id");
		if (confirm(__("Are you sure you want to delete this price?"))) {
			frappe.call({
				method: "frappe.client.delete",
				args: { doctype: "Item Price", name: price_id },
				callback: function () {
					frappe.show_alert({
						message: __("Price deleted successfully"),
						indicator: "green",
					});
					// Refresh the dialog to show updated prices
					getItemPricesAndOpenDialog(frm);
				},
			});
		}
	});

	dialog.$wrapper.on("click", ".add-price-btn", function () {
		const item_code = $(this).data("item-code");
		show_new_price_dialog(item_code, frm);
	});

	dialog.show();
}

function show_new_price_dialog(item_code, frm) {
	let new_dialog = new frappe.ui.Dialog({
		title: __("Add New Item Price"),
		fields: [
			{
				label: __("Price List"),
				fieldname: "price_list",
				fieldtype: "Link",
				options: "Price List",
				reqd: 1,
				filters: { selling: 1 },
			},
			{ label: __("Price"), fieldname: "price_list_rate", fieldtype: "Currency", reqd: 1 },
			{ label: __("Valid From"), fieldname: "valid_from", fieldtype: "Date", reqd: 1 },
			{ label: __("Valid Until"), fieldname: "valid_upto", fieldtype: "Date" },
		],
		primary_action_label: __("Save"),
		primary_action: function () {
			let values = new_dialog.get_values();
			if (!values) return;

			frappe.call({
				method: "frappe.client.insert",
				args: {
					doc: {
						doctype: "Item Price",
						item_code: item_code,
						price_list_rate: values.price_list_rate,
						price_list: values.price_list,
						selling: 1,
						valid_from: values.valid_from,
						valid_upto: values.valid_upto || null,
						currency: frappe.defaults.get_default("Currency"),
					},
				},
				callback: function () {
					frappe.show_alert({
						message: __("Price created successfully"),
						indicator: "green",
					});
					new_dialog.hide();
					// Refresh the main dialog
					getItemPricesAndOpenDialog(frm);
				},
			});
		},
	});

	new_dialog.set_values({
		item_code: item_code,
		valid_from: frappe.datetime.get_today(),
	});

	new_dialog.show();
}

function edit_price(price_id, item_code) {
	frappe.set_route("Form", "Item Price", price_id);
}
