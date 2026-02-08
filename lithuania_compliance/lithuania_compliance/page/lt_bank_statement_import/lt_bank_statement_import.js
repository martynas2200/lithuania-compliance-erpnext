// TODO: Make into a frappe doctype form like COA. With more user feedback
frappe.pages["lt-bank-statement-import"].on_page_load = function (wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: __("LT Bank Statement Import"),
        single_column: true,
    });

    frappe.lt_bank_statement_import.make(page);
    frappe.lt_bank_statement_import.run();

    frappe.breadcrumbs.add("lithuania_compliance");
};

frappe.lt_bank_statement_import = {
    start: 0,
    make: function (page) {
        var me = frappe.lt_bank_statement_import;
        me.page = page;
        me.body = $("<div></div>").appendTo(me.page.main);
        var data = "";
        $(frappe.render_template("lt_bank_statement_import", data)).appendTo(me.body);
    },
    run: function () {
        // wire up client-side behaviour for the form + import logs
        var $file_input = $("#lt_bank_file");
        var $desc_input = $("#lt_bank_description");
        var $auto_submit = $("#lt_bank_auto_submit");
        var $submit_btn = $("#lt_bank_submit");
        var $feedback = $("#lt_bank_feedback");
        var $log = $("#lt_bank_log");

        if (!$submit_btn.length) return;

        $submit_btn.on("click", function () {
            $feedback.empty();
            $log.empty();

            var file = $file_input[0] && $file_input[0].files && $file_input[0].files[0];
            var description = $desc_input.val();
            var auto_submit = $auto_submit.is(":checked");

            if (!file) {
                frappe.msgprint({
                    message: __("Please choose a file before importing."),
                    indicator: "red",
                });
                $feedback.html('<div class="text-danger">' + __("No file selected.") + "</div>");
                return;
            }

            $feedback.html('<div class="text-muted">' + __("Reading file...") + "</div>");

            var reader = new FileReader();
            reader.onload = function (event) {
                var content = event.target.result;
                $feedback.html(
                    '<div class="text-muted">' +
                        __("Uploading and processing statement...") +
                        "</div>"
                );

                frappe.call({
                    method: "lithuania_compliance.lithuania_compliance.page.lt_bank_statement_import.lt_bank_statement_import.import_camt_statement",
                    args: {
                        content: content,
                        description: description || null,
                        auto_submit: auto_submit ? 1 : 0,
                    },
                    freeze: true,
                    freeze_message: auto_submit
                        ? __("Importing and submitting bank statement...")
                        : __("Importing bank statement..."),
                    callback: function (r) {
                        if (!r.message) {
                            $feedback.html(
                                '<div class="text-danger">' +
                                    __("No response from server.") +
                                    "</div>"
                            );
                            return;
                        }

                        $feedback.html(
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

                        $log.html(html);
                    },
                });
            };

            reader.onerror = function () {
                $feedback.html(
                    '<div class="text-danger">' + __("Could not read file.") + "</div>"
                );
            };

            reader.readAsText(file, "utf-8");
        });
    },
};
