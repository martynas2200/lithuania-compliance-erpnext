// TODO: ADD a column where VAT classification code can be shown/edited

frappe.pages["isaf-generation"].on_page_load = function (wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: __("i.SAF XML Generation"),
        single_column: true,
    });
    $(frappe.render_template("isaf_generation")).appendTo(page.main);

    if (!frappe.ISAFGenerationWizard) {
        console.error("ISAFGenerationWizard is not defined");
        return;
    }
    frappe.ISAFGenerationWizard.setup(page);
};

frappe.ISAFGenerationWizard = {
    setup(page) {
        this.page = page;
        this.wrapper = page.main;
        this.current_step = 1;
        this.data = {
            export_type: null,
            year: null,
            month: null,
            from_date: null,
            to_date: null,
            excluded_invoices: [],
        };

        // Create a container for dynamic content (separate from templates)
        this.content_wrapper = $('<div class="wizard-content"></div>').appendTo(this.wrapper);

        this.render_wizard();
    },

    render_wizard() {
        this.content_wrapper.empty();

        // Progress indicator
        this.content_wrapper.append(this.get_progress_html());

        // Render current step
        switch (this.current_step) {
            case 1:
                this.render_export_type_step();
                break;
            case 2:
                this.render_period_selection_step();
                break;
            case 3:
                this.render_invoice_review_step();
                break;
            case 4:
                this.render_generation_step();
                break;
        }
    },

    get_progress_html() {
        const steps = [
            { num: 1, label: "Export Type" },
            { num: 2, label: "Period" },
            { num: 3, label: "Review Invoices" },
            { num: 4, label: "Generate" },
        ];

        let steps_html = "";

        steps.forEach((step, idx) => {
            const is_active = step.num === this.current_step;
            const is_completed = step.num < this.current_step;
            const status_class = is_active ? "active" : is_completed ? "completed" : "pending";
            const connector_class = is_completed ? "completed" : "pending";

            steps_html += `
				<div class="wizard-step ${status_class}">
					<div class="step-circle">
						${is_completed ? "✓" : step.num}
					</div>
					<div class="text-xs" style="${is_active ? "color: var(--primary);" : "color: #6b7280;"}">
						${__(step.label)}
					</div>
				</div>
				${
                    idx < steps.length - 1
                        ? `
					<div class="step-connector ${connector_class}"></div>
				`
                        : ""
                }
			`;
        });

        const $progress = $(".wizard-progress-template").clone().removeClass("hidden");
        $progress.find("div > div").html(steps_html);
        return $progress;
    },

    render_export_type_step() {
        const $template = $(".export-type-step-template").clone().removeClass("hidden");
        this.content_wrapper.append($template);

        // Add click handlers
        this.content_wrapper.find(".export-option").on("click", (e) => {
            const option = $(e.currentTarget);
            this.content_wrapper
                .find(".export-option")
                .css("border-color", "#d1d5db")
                .css("background", "white");
            option
                .css("border-color", "var(--primary)")
                .css("background", "var(--primary-light, #eff6ff)");
            this.data.export_type = option.data("type");
        });

        this.add_navigation_buttons();
    },

    render_period_selection_step() {
        const current_year = new Date().getFullYear();
        const years = [];
        for (let i = 0; i < 5; i++) {
            years.push(current_year - i);
        }

        const months = [
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ];

        const $template = $(".period-selection-step-template").clone().removeClass("hidden");

        // Populate years
        const year_options = years.map((y) => `<option value="${y}">${y}</option>`).join("");
        $template.find("#year-select").append(year_options);

        // Populate months
        const month_options = months
            .map((m, idx) => `<option value="${idx + 1}">${m}</option>`)
            .join("");
        $template.find("#month-select").append(month_options);

        this.content_wrapper.append($template);

        // Set current values if any
        if (this.data.year) {
            this.content_wrapper.find("#year-select").val(this.data.year);
        }
        if (this.data.month) {
            this.content_wrapper.find("#month-select").val(this.data.month);
        }

        // Add change handlers
        const update_preview = () => {
            const year = this.content_wrapper.find("#year-select").val();
            const month = this.content_wrapper.find("#month-select").val();

            if (year && month) {
                this.data.year = parseInt(year);
                this.data.month = parseInt(month);

                // Calculate date range
                const from_date = new Date(year, month - 1, 1);
                const to_date = new Date(year, month, 0);

                this.data.from_date = frappe.datetime.str_to_obj(from_date);
                this.data.to_date = frappe.datetime.str_to_obj(to_date);

                this.content_wrapper
                    .find("#date-range-display")
                    .text(
                        frappe.datetime.str_to_user(from_date) +
                            " to " +
                            frappe.datetime.str_to_user(to_date)
                    );
                this.content_wrapper.find("#date-preview").removeClass("hidden");
            } else {
                this.content_wrapper.find("#date-preview").addClass("hidden");
            }
        };

        this.content_wrapper.find("#year-select, #month-select").on("change", update_preview);
        update_preview();

        this.add_navigation_buttons();
    },

    render_invoice_review_step() {
        const $template = $(".invoice-review-step-template").clone().removeClass("hidden");
        this.content_wrapper.append($template);

        // Load invoices
        this.load_invoices();

        this.add_navigation_buttons();
    },

    load_invoices() {
        const doctype =
            this.data.export_type === "receivable" ? "Sales Invoice" : "Purchase Invoice";
        const party_field = this.data.export_type === "receivable" ? "customer" : "supplier";

        frappe.call({
            method: "frappe.client.get_list",
            args: {
                doctype: doctype,
                filters: {
                    posting_date: [
                        "between",
                        [
                            frappe.datetime.obj_to_str(this.data.from_date),
                            frappe.datetime.obj_to_str(this.data.to_date),
                        ],
                    ],
                    docstatus: 1,
                },
                fields: [
                    "name",
                    "posting_date",
                    party_field,
                    "grand_total",
                    "total_taxes_and_charges",
                ],
                limit_page_length: 0,
                order_by: "posting_date desc",
            },
            callback: (r) => {
                this.content_wrapper.find(".alert-warning").hide();
                this.content_wrapper.find("#invoice-list-container").removeClass("hidden");

                if (r.message && r.message.length > 0) {
                    this.invoices = r.message;
                    this.render_invoice_table(r.message);
                } else {
                    this.content_wrapper.find("#invoice-table-body").html(`
						<tr>
							<td colspan="6" class="text-center p-5">
								No invoices found for the selected period
							</td>
						</tr>
					`);
                }
            },
        });
    },

    render_invoice_table(invoices) {
        this.content_wrapper.find("#invoice-count").text(`${invoices.length} invoice(s) found`);

        let rows = "";
        invoices.forEach((invoice) => {
            const is_excluded = this.data.excluded_invoices.includes(invoice.name);
            const party = invoice.customer || invoice.supplier;
            const vat = frappe.format(invoice.total_taxes_and_charges, { fieldtype: "Currency" });

            rows += `
				<tr data-invoice="${invoice.name}">
					<td class="text-center">
						<input type="checkbox" class="invoice-checkbox"
							data-invoice="${invoice.name}"
							${!is_excluded ? "checked" : ""}>
					</td>
					<td><a href="/app/${invoice.doctype.toLowerCase().replace(" ", "-")}/${
                invoice.name
            }" target="_blank">${invoice.name}</a></td>
					<td>${frappe.datetime.str_to_user(invoice.posting_date)}</td>
					<td>${party}</td>
					<td class="text-right">${frappe.format(invoice.grand_total, { fieldtype: "Currency" })}</td>
					<td class="text-right">${vat}</td>
				</tr>
			`;
        });

        this.content_wrapper.find("#invoice-table-body").html(rows);

        // Add event handlers
        this.content_wrapper.find(".invoice-checkbox").on("change", (e) => {
            const invoice_name = $(e.target).data("invoice");
            if ($(e.target).is(":checked")) {
                // Remove from excluded list
                this.data.excluded_invoices = this.data.excluded_invoices.filter(
                    (n) => n !== invoice_name
                );
            } else {
                // Add to excluded list
                if (!this.data.excluded_invoices.includes(invoice_name)) {
                    this.data.excluded_invoices.push(invoice_name);
                }
            }
            this.update_excluded_summary();
        });

        this.content_wrapper.find("#select-all-btn").on("click", () => {
            this.content_wrapper.find(".invoice-checkbox").prop("checked", true);
            this.data.excluded_invoices = [];
            this.update_excluded_summary();
        });

        this.content_wrapper.find("#deselect-all-btn").on("click", () => {
            this.content_wrapper.find(".invoice-checkbox").prop("checked", false);
            this.data.excluded_invoices = this.invoices.map((inv) => inv.name);
            this.update_excluded_summary();
        });

        this.update_excluded_summary();
    },

    update_excluded_summary() {
        const excluded_count = this.data.excluded_invoices.length;
        if (excluded_count > 0) {
            this.content_wrapper.find("#excluded-count").text(excluded_count);
            this.content_wrapper.find("#excluded-summary").removeClass("hidden");
        } else {
            this.content_wrapper.find("#excluded-summary").addClass("hidden");
        }
    },

    render_generation_step() {
        const included_count = (this.invoices?.length || 0) - this.data.excluded_invoices.length;

        const $template = $(".generation-step-template").clone().removeClass("hidden");

        // Populate summary table
        const summary_rows = `
			<tr>
				<td><strong>${__("Export Type:")}</strong></td>
				<td>${this.data.export_type === "receivable" ? "Received Invoices" : "Issued Invoices"}</td>
			</tr>
			<tr>
				<td><strong>${__("Period:")}</strong></td>
				<td>${frappe.datetime.obj_to_user(this.data.from_date)} to ${frappe.datetime.obj_to_user(
            this.data.to_date
        )}</td>
			</tr>
			<tr>
				<td><strong>${__("Invoices to Include:")}</strong></td>
				<td>${included_count} invoice(s)</td>
			</tr>
			<tr>
				<td><strong>${__("Invoices Excluded:")}</strong></td>
				<td>${this.data.excluded_invoices.length} invoice(s)</td>
			</tr>
		`;
        $template.find("#summary-table-body").html(summary_rows);

        this.content_wrapper.append($template);

        this.content_wrapper.find("#generate-btn").on("click", () => {
            this.generate_xml();
        });

        this.add_navigation_buttons();
    },

    generate_xml() {
        this.content_wrapper.find("#generate-btn").hide();
        this.content_wrapper.find("#generation-progress").removeClass("hidden");

        frappe.call({
            method: "lithuania_compliance.api.isaf.generate_isaf_xml",
            args: {
                export_type: this.data.export_type,
                from_date: frappe.datetime.obj_to_str(this.data.from_date),
                to_date: frappe.datetime.obj_to_str(this.data.to_date),
                excluded_invoices: this.data.excluded_invoices,
            },
            callback: (r) => {
                this.content_wrapper.find("#generation-progress").addClass("hidden");

                if (r.message && r.message.success) {
                    this.content_wrapper
                        .find("#generation-result")
                        .html(
                            `
						<div class="alert alert-success">
							<h5><i class="fa fa-check-circle"></i> Success!</h5>
							<p>i.SAF XML file has been generated successfully.</p>
							<p class="mt-4">
								<a href="${r.message.file_url}" class="btn btn-success" download>
									<i class="fa fa-download"></i> Download XML File
								</a>
							</p>
							<p class="mt-2 text-xs" style="color: #6b7280;">
								File: ${r.message.file_name}
							</p>
						</div>
					`
                        )
                        .removeClass("hidden");
                } else {
                    this.content_wrapper.find("#generate-btn").show();
                    this.content_wrapper
                        .find("#generation-result")
                        .html(
                            `
						<div class="alert alert-danger">
							<h5><i class="fa fa-exclamation-triangle"></i> Generation Failed</h5>
							<p>${r.message?.error || "An error occurred while generating the XML file."}</p>
						</div>
					`
                        )
                        .removeClass("hidden");
                }
            },
            error: () => {
                this.content_wrapper.find("#generation-progress").addClass("hidden");
                this.content_wrapper.find("#generate-btn").show();
                this.content_wrapper
                    .find("#generation-result")
                    .html(
                        `
					<div class="alert alert-danger">
						<p>The i.SAF generation feature is not yet fully implemented.</p>
					</div>
				`
                    )
                    .removeClass("hidden");
            },
        });
    },

    add_navigation_buttons() {
        const $template = $(".navigation-buttons-template").clone().removeClass("hidden");

        // Configure buttons based on current step
        if (this.current_step === 1) {
            $template.find("#prev-btn").prop("disabled", true);
        }
        if (this.current_step === 4) {
            $template.find("#next-btn").hide();
        }

        // Attach event handlers to the cloned template before appending
        $template.find("#prev-btn").on("click", () => {
            if (this.current_step > 1) {
                this.current_step--;
                this.render_wizard();
            }
        });

        $template.find("#next-btn").on("click", () => {
            if (this.validate_current_step()) {
                this.current_step++;
                this.render_wizard();
            }
        });

        this.content_wrapper.append($template);
    },

    validate_current_step() {
        switch (this.current_step) {
            case 1:
                if (!this.data.export_type) {
                    frappe.msgprint("Please select an export type");
                    return false;
                }
                break;
            case 2:
                if (!this.data.year || !this.data.month) {
                    frappe.msgprint("Please select both year and month");
                    return false;
                }
                break;
            case 3:
                // Optional - user can exclude all if they want
                break;
        }
        return true;
    },
};
