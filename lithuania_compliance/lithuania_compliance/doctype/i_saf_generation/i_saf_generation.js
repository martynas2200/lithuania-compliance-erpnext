// Copyright (c) 2026, Martynas Miliauskas and contributors
// For license information, please see license.txt

frappe.ui.form.on("i-SAF Generation", {
    onload: function (frm) {
        if (!frm.doc.company) {
            frm.set_value("company", frappe.defaults.get_default("company"));
        }
        let today = frappe.datetime.get_today();
        let previous_month = frappe.datetime.add_months(today, -1);
        let month = frappe.datetime
            .str_to_obj(previous_month)
            .toLocaleString("en-US", { month: "long" });
        frm.set_value("month", month);
        frm.set_value("year", frappe.datetime.str_to_obj(previous_month).getFullYear());
    },
    refresh: function (frm) {
        frm.disable_save();
        frm.add_custom_button(__("Generate"), () => frm.trigger("generate_isaf_xml"));
        frm.change_custom_button_type(__("Generate"), null, "primary");
    },
    generate_isaf_xml: function (frm) {
        if (!frm.doc.company || !frm.doc.year || !frm.doc.month || !frm.doc.register_type) {
            frappe.msgprint(__("Please fill all required fields"));
            return;
        }
        // register type could be 'issued', 'received' or 'both'
        let register_type = frm.doc.register_type.toLowerCase();
        register_type = register_type.split(" ")[0];
        frm.page.set_indicator(__("Generating"), "orange");
        frm.remove_custom_button(__("Generate"));
        frappe.call({
            method: "lithuania_compliance.api.isaf.generate_isaf_xml",
            args: {
                company: frm.doc.company,
                export_type: register_type,
                year: frm.doc.year,
                month: frm.doc.month,
            },
            callback: function (r) {
                if (r.message && r.message.success) {
                    frm.page.set_indicator(__("Generated"), "green");
                    frm.add_custom_button(__("Generate"), () => frm.trigger("generate_isaf_xml"));
                    frappe.msgprint({
                        message: `
                            <div style="display: grid; grid-template-columns: 150px auto; gap: 4px 12px;">
                                <div>${__("Period")}:</div>
                                <div>${__(frm.doc.month)} ${frm.doc.year}</div>
                                <div>${__("Register Type")}:</div>
                                <div>${__(frm.doc.register_type)}</div>
                                <div>${__("Total Invoices")}:</div>
                                <div>${r.message.total_invoices}</div>
                            </div>
                            <hr/>
                            <div class="alert alert-success text-center">
                                <p>${__("i.SAF XML file has been generated successfully.")}</p>
                                <p class="mt-4 center-content">
                                    <a href="${
                                        r.message.file_url
                                    }" class="btn btn-success" download>
                                        <i class="fa fa-download"></i> ${__("Download")} XML ${__(
                            "File"
                        )}
                                    </a>
                                </p>
                                <p class="mt-2 text-xs" style="color: #6b7280;">
                                    ${r.message.file_name}
                                </p>
                            </div>`,
                        title: __("Compiled Successfully"),
                        indicator: "green",
                    });
                }
            },
            error: function (err) {
                frappe.msgprint({
                    message: err.message || __("An error occurred while generating the XML file."),
                    title: __("Error generating i.SAF XML file."),
                    indicator: "red",
                });
            },
        });
    },
});
