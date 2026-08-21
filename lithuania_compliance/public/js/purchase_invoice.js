const lithuaniaCompliance = frappe.provide("lithuania_compliance");

let itemPricesApp = null;
let itemPricesRootComponent = null;

frappe.ui.form.on("Purchase Invoice", {
    refresh(frm) {
        if (!frm.is_new() && frm.doc.docstatus === 0) {
            frm.add_custom_button(
                __("Item Prices"),
                getItemPricesAndOpenDialog.bind(null, frm, true),
                __("Preview")
            );
            frm.add_custom_button(
                __("i.SAF Record"),
                () => lithuaniaCompliance.isaf.fetch_and_show_totals(frm),
                __("Preview")
            );
        } else if (!frm.is_new()) {
            frm.add_custom_button(
                __("Item Prices"),
                getItemPricesAndOpenDialog.bind(null, frm, true),
                __("View")
            );
            frm.add_custom_button(
                __("i.SAF Record"),
                () => lithuaniaCompliance.isaf.fetch_and_show_totals(frm),
                __("View")
            );
        }
    },
    on_submit(frm) {
        check_buying_prices(frm);
    },
});

async function check_buying_prices(frm) {
    const result = await frappe.call({
        method: "lithuania_compliance.api.purchase_invoice.get_changed_buying_prices",
        args: {
            invoice_name: frm.docname,
        },
    });
    const changed_items = result.message;
    if (!changed_items?.length) return;

    const escapeHtml = (value) =>
        $("<div>")
            .text(value == null ? "" : String(value))
            .html();
    const formatMoney = (value, currency) =>
        frappe.format(value, {
            fieldtype: "Currency",
            options: currency || frappe.boot.sysdefaults.currency,
        });

    const renderRow = (item) => {
        const diff = item.invoice_rate - item.current_buying_price;
        const diffClass = diff > 0 ? "text-danger" : "text-success";
        return `
            <tr>
                <td class="text-center">
                    <input type="checkbox" id="item_${item.item_code}" checked>
                </td>
                <td>
                    <div>${escapeHtml(item.item_name)}</div>
                    <div class="text-muted small">${escapeHtml(item.item_code)}</div>
                </td>
                <td class="text-right">${formatMoney(item.invoice_rate, item.currency)}</td>
                <td class="text-right">${formatMoney(
                    item.current_buying_price,
                    item.currency
                )}</td>
                <td class="text-right ${diffClass}">${formatMoney(diff, item.currency)}</td>
                <td>${escapeHtml(item.valid_from)}</td>
                <td>${escapeHtml(item.valid_upto)}</td>
            </tr>`;
    };

    // Create a dialog where you can select which items to update the buying prices for
    const d = new frappe.ui.Dialog({
        title: __("Update Buying Prices"),
        fields: [
            {
                fieldtype: "HTML",
                fieldname: "items_html",
            },
        ],
        primary_action_label: __("Update"),
        primary_action: () => {
            const selected_codes = changed_items
                .filter((item) =>
                    d.fields_dict.items_html.$wrapper
                        .find(`#${CSS.escape(`item_${item.item_code}`)}`)
                        .is(":checked")
                )
                .map((item) => item.item_code);
            update_buying_prices(frm.doc, selected_codes);
            d.hide();
        },
        secondary_action_label: __("Cancel"),
        secondary_action: () => {
            d.hide();
        },
    });
    const items_html = `
        <div role="alert">
            ${__(
                "The buying price for these items is lower than the invoice rate. Select the items to record a new buying price from today; existing prices are preserved as history."
            )}
        </div>
        <table class="table table-bordered table-hover" style="margin-bottom: 0;">
            <thead>
                <tr>
                    <th style="width: 36px;"></th>
                    <th>${__("Item")}</th>
                    <th class="text-right">${__("Invoice Rate")}</th>
                    <th class="text-right">${__("Buying Price")}</th>
                    <th class="text-right">${__("Difference")}</th>
                    <th>${__("Valid From")}</th>
                    <th>${__("Valid Upto")}</th>
                </tr>
            </thead>
            <tbody>
                ${changed_items.map(renderRow).join("")}
            </tbody>
        </table>`;

    d.fields_dict.items_html.$wrapper.html(items_html);
    d.show();
}

const update_buying_prices = (invoice, item_codes) => {
    frappe.call({
        method: "lithuania_compliance.api.purchase_invoice.update_buying_prices",
        args: {
            invoice_name: invoice.name,
            item_codes,
        },
        callback: () => {
            frappe.toast({
                message: __("Buying prices updated successfully"),
                indicator: "green",
            });
        },
    });
};

function getItemPricesAndOpenDialog(frm, forced = false) {
    // If app already exists, just update its state and show it
    if (itemPricesApp && itemPricesRootComponent) {
        itemPricesRootComponent.invoiceName = frm.doc.name;
        itemPricesRootComponent.frm = frm;
        itemPricesRootComponent.forced = forced;
        itemPricesRootComponent.isOpenState = true;
        return;
    }

    show_manage_prices_dialog(frm, forced);
}

async function show_manage_prices_dialog(frm, forced = false) {
    // Create container for Vue app
    const modalContainer = document.createElement("div");
    modalContainer.id = "item-prices-modal-container";
    document.body.appendChild(modalContainer);

    try {
        if (!frappe.ui.ItemPricesModal) {
            await frappe.require("item_prices_modal.bundle.js");
        }

        const RootComponent = {
            template: `
                <ItemPricesModal
                    :isOpen="isOpenState"
                    :invoiceName="invoiceName"
                    :frm="frm"
                    :forced="forced"
                    @close="handleClose"
                    @reopen="handleReopen"
                />
            `,
            data() {
                return {
                    isOpenState: true,
                    invoiceName: frm.doc.name,
                    frm: frm,
                    forced: forced,
                };
            },
            methods: {
                handleClose() {
                    this.isOpenState = false;
                },
                handleReopen() {
                    this.isOpenState = true;
                },
            },
        };

        const app = frappe.ui.setup_vue(RootComponent);

        // Register the ItemPricesModal component
        app.component("ItemPricesModal", frappe.ui.ItemPricesModal);

        // Mount the app and store both the app instance and root component
        const rootInstance = app.mount(modalContainer);
        itemPricesApp = app;
        itemPricesRootComponent = rootInstance;
    } catch (err) {
        console.error("Failed to setup ItemPricesModal:", err);
        frappe.msgprint(__("Error loading modal."));
        modalContainer.remove();
    }
}
