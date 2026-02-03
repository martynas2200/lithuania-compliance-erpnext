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
                this.render_generation_step();
                break;
        }
        this.add_navigation_buttons();
    },

    get_progress_html() {
        const steps = [
            { num: 1, label: "Export Type" },
            { num: 2, label: "Period" },
            { num: 3, label: "Done" },
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
    },

    render_period_selection_step() {
        const current_year = new Date().getFullYear();
        const years = [];
        for (let i = 0; i < 5; i++) {
            years.push(current_year - i);
        }

        const months = [
            __("January"),
            __("February"),
            __("March"),
            __("April"),
            __("May"),
            __("June"),
            __("July"),
            __("August"),
            __("September"),
            __("October"),
            __("November"),
            __("December"),
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
    },

    render_generation_step() {
        const $template = $(".generation-step-template").clone().removeClass("hidden");
        this.content_wrapper.append($template);
        this.generate_xml();
    },

    generate_xml() {
        frappe.call({
            method: "lithuania_compliance.api.isaf.generate_isaf_xml",
            args: {
                export_type: this.data.export_type,
                from_date: frappe.datetime.obj_to_str(this.data.from_date),
                to_date: frappe.datetime.obj_to_str(this.data.to_date),
            },
            callback: (r) => {
                if (r.message && r.message.success) {
                    this.content_wrapper.find("#generation-status").html(
                        `
						<div class="alert alert-success">
							<h5><i class="fa fa-check-circle"></i> ${__("Compiled Successfully")}</h5>
                            <p>${__("Period")}: ${frappe.datetime.str_to_user(
                            frappe.datetime.obj_to_str(this.data.from_date)
                        )} - ${frappe.datetime.str_to_user(
                            frappe.datetime.obj_to_str(this.data.to_date)
                        )}</p>
                            <p>${__("Export Type")}: ${__(
                            this.data.export_type.charAt(0).toUpperCase() +
                                this.data.export_type.slice(1)
                        )}</p>
                            <p>${__("Total Invoices")}: ${r.message.total_invoices}</p>
                            <hr/>
							<p>${__("i.SAF XML file has been generated successfully.")}</p>
							<p class="mt-4">
								<a href="${r.message.file_url}" class="btn btn-success" download>
									<i class="fa fa-download"></i> ${__("Download")} XML ${__("File")}
								</a>
							</p>
							<p class="mt-2 text-xs" style="color: #6b7280;">
								${__("File")}: ${r.message.file_name}
							</p>
						</div>
					`
                    );
                }
            },
            error: () => {
                this.content_wrapper
                    .find("#generation-status")
                    .html(
                        `<div class="text-center">${__(
                            "An error occurred while generating the XML file."
                        )}</div>`
                    );
            },
        });
    },

    add_navigation_buttons() {
        const $template = $(".navigation-buttons-template").clone().removeClass("hidden");

        if (this.current_step === 1) {
            $template.find("#prev-btn").prop("disabled", true);
        }
        if (this.current_step === 3) {
            $template.find("#next-btn").text(__("Start Over"));
        }

        $template.find("#prev-btn").on("click", () => {
            if (this.current_step > 1) {
                this.current_step--;
                this.render_wizard();
            }
        });

        $template.find("#next-btn").on("click", () => {
            if (this.current_step === 3) {
                // Restart the wizard
                this.current_step = 1;
                this.data = {
                    export_type: null,
                    year: null,
                    month: null,
                    from_date: null,
                    to_date: null,
                };
                this.render_wizard();
                return;
            }
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
        }
        return true;
    },
};
