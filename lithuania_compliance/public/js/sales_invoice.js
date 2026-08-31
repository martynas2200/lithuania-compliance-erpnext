const lithuaniaCompliance = frappe.provide("lithuania_compliance");

frappe.ui.form.on("Sales Invoice", {
    refresh: function (frm) {
        if (frm.is_new() || frm.doc.docstatus !== 0) {
            return;
        }

        frm.add_custom_button(
            __("i.SAF Record"),
            () => lithuaniaCompliance.isaf.fetch_and_show_totals(frm),
            __("View")
        );
    },
});
