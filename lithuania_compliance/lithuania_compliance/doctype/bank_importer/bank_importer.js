var set_preview_html = function (frm, html) {
    var field = frm.get_field("preview_html");
    if (field) {
        field.$wrapper.html(html || "");
    }
};

frappe.ui.form.on("Bank Importer", {
    onload: function (frm) {
        frm.set_value("company", "");
        frm.set_value("import_file", "");
        frm.import_file_content = null;
    },
    refresh: function (frm) {
        frm.disable_save();

        frm.set_df_property("company", "reqd", frm.doc.company ? 0 : 1);
        frm.set_df_property("import_file_section", "hidden", frm.doc.company ? 0 : 1);

        if (frm.doc.import_file) {
            create_import_button(frm);
        }
    },

    import_file: function (frm) {
        frm.import_file_content = null;

        if (!frm.doc.import_file) {
            frm.page.set_indicator("");
            set_preview_html(frm, "");
            return;
        }

        resolve_import_file_content(frm)
            .then(function (content) {
                frm.import_file_content = content;

                // Show loading indicator
                set_preview_html(
                    frm,
                    '<div class="text-muted">' + __("Parsing transactions...") + "</div>"
                );

                return frappe.call({
                    method: "lithuania_compliance.lithuania_compliance.doctype.bank_importer.bank_importer.preview_camt",
                    args: {
                        content: content,
                    },
                    freeze: false,
                });
            })
            .then(function (r) {
                if (!r || !r.message) {
                    set_preview_html(frm, "");
                    return;
                }

                var data = r.message;
                var txns = data.transactions || [];

                var html = build_preview_html(data, txns);
                set_preview_html(frm, html);
            })
            .catch(function () {
                // Fallback: just show count client-side
                if (frm.import_file_content) {
                    var count = (frm.import_file_content.match(/<ntry>/g) || []).length;
                    var html =
                        "<div class='alert alert-info'>" +
                        __("Found {0} &lt;ntry&gt; entries in the file.", [count]) +
                        "</div>";
                    set_preview_html(frm, html);
                } else {
                    set_preview_html(frm, "");
                }
            });
    },

    company: function (frm) {
        // prefill the last import date here
        // frm.set_value("last_import_date", "");
    },
});

var create_import_button = function (frm) {
    frm.page
        .set_primary_action(__("Import"), function () {
            return resolve_import_file_content(frm)
                .then(function (content) {
                    frm.import_file_content = content;

                    return frappe.call({
                        method: "lithuania_compliance.lithuania_compliance.doctype.bank_importer.bank_importer.import_camt_statement",
                        args: {
                            content: content,
                            auto_submit: frm.doc.auto_submit ? 1 : 0,
                        },
                        freeze: true,
                        freeze_message: __("Importing bank statement..."),
                        callback: function (r) {
                            if (!r.message) {
                                frappe.msgprint(
                                    '<div class="text-danger">' +
                                        __("No response from server.") +
                                        "</div>"
                                );
                                return;
                            }

                            frappe.msgprint(
                                '<div class="alert alert-info">' +
                                    frappe.utils.escape_html(r.message.summary || "") +
                                    "</div>"
                            );

                            var records = r.message.records || [];
                            var errors = r.message.errors || [];

                            var html = "";
                            if (records.length) {
                                html += "<h4>" + __("Created Payment Entries") + "</h4>";
                                html += "<ul>";
                                records.forEach(function (pe) {
                                    html +=
                                        '<li><a href="/app/payment-entry/' +
                                        encodeURIComponent(pe) +
                                        '" target="_blank">' +
                                        frappe.utils.escape_html(pe) +
                                        "</a></li>";
                                });
                                html += "</ul>";
                            }

                            if (errors.length) {
                                html += "<h4>" + __("Import Errors") + "</h4>";
                                html += '<ul class="text-danger">';
                                errors.forEach(function (err) {
                                    html += "<li>" + frappe.utils.escape_html(err) + "</li>";
                                });
                                html += "</ul>";
                            }

                            if (!html) {
                                html =
                                    '<div class="text-muted">' +
                                    __("Nothing was imported.") +
                                    "</div>";
                            }

                            frappe.msgprint(html);
                        },
                    });
                })
                .catch(function (error) {
                    frappe.msgprint(
                        '<div class="text-danger">' +
                            frappe.utils.escape_html(
                                error.message || __("Could not read import file.")
                            ) +
                            "</div>"
                    );
                });
        })
        .addClass("btn btn-primary");
};

var resolve_import_file_content = function (frm) {
    if (frm.import_file_content) {
        return Promise.resolve(frm.import_file_content);
    }

    var file_input = $("input[data-fieldname='import_file']")[0];
    if (file_input && file_input.files && file_input.files[0]) {
        return read_file_as_text(file_input.files[0]);
    }

    if (frm.doc.import_file) {
        return fetch(frm.doc.import_file).then(function (response) {
            if (!response.ok) {
                throw new Error(__("Could not load attached file."));
            }

            return response.text();
        });
    }

    return Promise.reject(new Error(__("No import file selected.")));
};

var read_file_as_text = function (file) {
    return new Promise(function (resolve, reject) {
        var reader = new FileReader();
        reader.onload = function (event) {
            resolve(event.target.result || "");
        };
        reader.onerror = function () {
            reject(new Error(__("Could not read file.")));
        };
        reader.readAsText(file, "utf-8");
    });
};

var build_preview_html = function (data, txns) {
    var html = "";

    // Summary bar
    var summary_class = "alert alert-info";
    if (data.total_credit > 0 && data.total_debit > 0) {
        summary_class = "alert alert-warning";
    }

    html +=
        "<div class='" +
        summary_class +
        "'>" +
        "<strong>" +
        __("Found {0} transaction(s)", [data.total_transactions]) +
        "</strong>" +
        "<br>" +
        __("Bank: {0}", [frappe.utils.escape_html(data.account || "")]) +
        "<br>" +
        "<span class='text-success'>" +
        __("Total incoming: {0}", [format_amount(data.total_credit)]) +
        "</span>" +
        " &nbsp; " +
        "<span class='text-danger'>" +
        __("Total outgoing: {0}", [format_amount(data.total_debit)]) +
        "</span>" +
        "</div>";

    if (!txns.length) {
        html += '<div class="text-muted">' + __("No transactions to display.") + "</div>";
        return html;
    }

    html += '<table class="table table-hover" style="margin-bottom: 0; font-size: 12px;">';
    html += "<thead><tr>";
    html += "<th>" + __("Date") + "</th>";
    html += "<th>" + __("Type") + "</th>";
    html += "<th>" + __("Amount") + "</th>";
    html += "<th>" + __("Party") + "</th>";
    html += "<th>" + __("Reference") + "</th>";
    html += "<th>" + __("Action") + "</th>";
    html += "<th>" + __("Match") + "</th>";
    html += "</tr></thead><tbody>";

    txns.forEach(function (txn) {
        var amount_class = txn.direction === "CRDT" ? "text-success" : "text-danger";
        var sign = txn.direction === "CRDT" ? "+" : "-";
        var party_cell = frappe.utils.escape_html(txn.party_name || "");
        if (txn.party_iban) {
            party_cell +=
                '<br><span class="text-muted" style="font-size: 10px;">' +
                frappe.utils.escape_html(txn.party_iban) +
                "</span>";
        }
        var match_cell = "";
        if (txn.matched_party) {
            match_cell =
                '<span class="label label-info">' +
                frappe.utils.escape_html(txn.matched_party) +
                "</span>";
            if (txn.matched_party_type) {
                match_cell +=
                    ' <span class="label label-default">' +
                    frappe.utils.escape_html(txn.matched_party_type) +
                    "</span>";
            }
        } else {
            match_cell = '<span class="text-muted">—</span>';
        }
        if (txn.reference_count > 0) {
            match_cell +=
                ' <span class="label label-success" title="' +
                __("Has invoice references") +
                '">' +
                __("{0} invoice(s)", [txn.reference_count]) +
                "</span>";
        }
        if (txn.subfamily_code) {
            match_cell +=
                ' <span class="label label-warning">' +
                frappe.utils.escape_html(txn.subfamily_code) +
                "</span>";
        }

        html += "<tr>";
        html += "<td>" + frappe.utils.escape_html(txn.date) + "</td>";
        html += "<td>" + frappe.utils.escape_html(txn.direction_label || txn.direction) + "</td>";
        html +=
            "<td class='" + amount_class + "'>" + sign + " " + format_amount(txn.amount) + "</td>";
        html += "<td>" + party_cell + "</td>";
        html +=
            "<td style='max-width: 150px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;' title='" +
            frappe.utils.escape_html(txn.remittance_reference) +
            "'>" +
            frappe.utils.escape_html(txn.remittance_reference) +
            "</td>";
        html += "<td>" + frappe.utils.escape_html(txn.action) + "</td>";
        html += "<td>" + match_cell + "</td>";
        html += "</tr>";

        // Show fee sub-row if charges exist
        if (txn.charges > 0) {
            html +=
                '<tr class="active"><td></td><td><span class="text-muted">' +
                __("Fee") +
                "</span></td>";
            html += '<td class="text-muted">-' + format_amount(txn.charges) + "</td>";
            html +=
                '<td colspan="4"><span class="text-muted">' +
                __("Bank charges will be split into a separate entry") +
                "</span></td></tr>";
        }
    });

    html += "</tbody></table>";

    return html;
};

var format_amount = function (value) {
    if (value === null || value === undefined) return "0.00";
    return parseFloat(value).toFixed(2);
};
