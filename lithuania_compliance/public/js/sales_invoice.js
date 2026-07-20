const lithuaniaCompliance = frappe.provide("lithuania_compliance");

frappe.ui.form.on("Sales Invoice", {
    refresh: function (frm) {
        if (frm.is_new() || frm.doc.docstatus !== 0) {
            return;
        }

        // TODO: Backend is not ready yet
        // frm.add_custom_button(
        // 	__("Generate Taxes from VAT Classificators"),
        // 	regenerate_taxes_from_vat_classificators.bind(null, frm),
        // 	__("Actions")
        // );

        frm.add_custom_button(
            __("i.SAF Record"),
            () => lithuaniaCompliance.isaf.fetch_and_show_totals(frm),
            __("Preview")
        );
    },
});

function regenerate_taxes_from_vat_classificators(frm) {
    frappe.confirm(
        __(
            "Current tax rows will be replaced using VAT classificators assigned to items. Continue?"
        ),
        async () => {
            const result = await frappe.call({
                method: "lithuania_compliance.api.isaf.regenerate_invoice_taxes_from_vat_classificators",
                args: {
                    doc_name: frm.docname,
                    doc_type: frm.doctype,
                },
                freeze: true,
                freeze_message: __("Generating taxes..."),
            });

            if (result?.message?.success) {
                frappe.show_alert(
                    {
                        message: __("Taxes regenerated: {0}", [result.message.taxes_count || 0]),
                        indicator: "green",
                    },
                    6
                );
                await frm.reload_doc();
            }
        }
    );
}
