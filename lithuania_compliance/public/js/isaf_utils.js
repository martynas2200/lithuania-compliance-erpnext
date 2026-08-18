frappe.provide("lithuania_compliance.isaf");

const lithuaniaCompliance = frappe.provide("lithuania_compliance");

lithuaniaCompliance.isaf.show_totals_modal = function (data) {
    if (!data || !Array.isArray(data)) {
        frappe.msgprint(__("No data to display."));
        return;
    }

    const infoId = frappe.dom.get_unique_id();
    const infoHtml = `<div class="mb-3">
            <div class="d-flex justify-content-end mb-2">
                <button class="btn btn-outline btn-xs collapsed" type="button" data-toggle="collapse" data-target="#${infoId}" aria-expanded="false" aria-controls="${infoId}">
                    ${__("Info")}
                </button>
            </div>
            <div class="collapse mt-2" id="${infoId}">
                <div class="alert alert-info mb-0">
                    <strong>${__("How values are determined")}</strong>
                    <ul class="mb-0">
                        <li>${__(
                            "Amount: first uses Purchase/Sales tax rows; if empty, checks the item's default classificator; if still empty, uses the default classificator from Settings menu."
                        )}</li>
                        <li>${__(
                            "Taxable Value: comes from fees table rows with Classificator set; if not set, uses the company's default from Settings."
                        )}</li>
                    </ul>
                </div>
            </div>
        </div>`;

    let html = `<table class="table table-bordered">
					<thead>
						<tr>
							<th>${__("VAT Classificator")}</th>
							<th>${__("Taxable Value")}</th>
							<th>${__("Amount")}</th>
							<th>${__("Rate (%)")}</th>
						</tr>
					</thead>
				<tbody>`;

    data.forEach((row) => {
        const amount = row.amount;
        const amountDisplay =
            amount === null || amount === undefined || parseFloat(amount) === 0
                ? ""
                : parseFloat(amount).toFixed(2);
        html += `<tr>
			<td>${frappe.utils.escape_html(row.tax_code)}</td>
			<td>${parseFloat(row.taxable_value).toFixed(2)}</td>
			<td>${amountDisplay}</td>
			<td>${row.tax_percentage == null ? "" : row.tax_percentage}</td>
		</tr>`;
    });

    html += "</tbody></table>" + infoHtml;

    frappe.msgprint({
        title: __("i.SAF Record"),
        indicator: "blue",
        message: html,
        wide: true,
    });
};

lithuaniaCompliance.isaf.fetch_and_show_totals = async function (frm) {
    const result = await frappe.call({
        method: "lithuania_compliance.api.isaf.get_isaf_totals",
        args: {
            doc_name: frm.docname,
            doc_type: frm.doctype,
        },
    });
    lithuaniaCompliance.isaf.show_totals_modal(result.message || result);
};
