<template>
    <div v-if="isOpen" class="item-prices-modal-overlay" @click.self="closeModal">
        <div class="item-prices-modal-dialog modal-content">
            <div class="modal-header">
                <div class="fill-width flex title-section">
                    <span class="indicator hidden"></span>
                    <h4 class="modal-title">{{ __("Manage Item Prices") }}</h4>
                </div>
                <div class="modal-actions">
                    <button
                        type="button"
                        class="btn btn-sm btn-default mr-2"
                        @click="refreshData"
                        :disabled="loading"
                    >
                        <i class="fa fa-refresh" :class="{ 'fa-spin': loading }"></i>
                        {{ __("Refresh") }}
                    </button>

                    <button
                        class="btn btn-modal-close btn-link"
                        data-dismiss="modal"
                        @click="closeModal"
                    >
                        <svg class="icon icon-sm" aria-hidden="true">
                            <use class="close-alt" href="#icon-close-alt"></use>
                        </svg>
                    </button>
                </div>
            </div>

            <div class="modal-body">
                <div v-if="loading" class="text-center p-5">
                    <i class="fa fa-spinner fa-spin fa-2x"></i>
                    <p class="mt-3">{{ __("Loading...") }}</p>
                </div>
                <div v-else class="manage-prices-container">
                    <table class="table table-bordered">
                        <thead>
                            <tr class="table-header-row">
                                <th>
                                    <div>
                                        <span>{{ __("Item Code") }}</span>
                                        <span class="pull-right">{{ __("Barcode") }}</span>
                                    </div>
                                    <span>{{ __("Name") }}</span>
                                </th>
                                <th>
                                    <div class="text-right">{{ __("Selling") }}</div>
                                    <div class="valid-range-text">
                                        {{ __("Valid") }}
                                    </div>
                                </th>
                                <th>{{ __("Markup") }}</th>
                                <th class="text-center">{{ __("Buying Rate") }}</th>
                                <th class="text-center">{{ __("Actions") }}</th>
                            </tr>
                        </thead>
                        <tbody>
                            <template v-for="item in itemsData" :key="item.item_code">
                                <tr
                                    :class="[
                                        'item-price-row',
                                        getMarkupClass(item.markup, !!item.applicable_price),
                                    ]"
                                >
                                    <td v-if="item.applicable_price">
                                        <a
                                            href="#"
                                            class="item-code-link"
                                            :data-item-code="item.item_code"
                                            @click.prevent="navigateToItem(item.item_code)"
                                        >
                                            <span>
                                                {{ item.item_code }}
                                                <span
                                                    v-if="hasMultiplePrices(item)"
                                                    class="multiple-prices-indicator"
                                                    >*</span
                                                >
                                            </span>
                                        </a>
                                        <span class="pull-right">{{ item.barcode }}</span>
                                        <div class="item-name-text">
                                            {{ item.item_name }}
                                        </div>
                                    </td>
                                    <td v-else>
                                        <a
                                            href="#"
                                            class="item-code-link"
                                            :data-item-code="item.item_code"
                                            @click.prevent="navigateToItem(item.item_code)"
                                        >
                                            <span>{{ item.item_code }}</span>
                                        </a>
                                        <span class="pull-right">{{ item.barcode }}</span>
                                        <div class="item-name-text">
                                            {{ item.item_name }}
                                        </div>
                                    </td>

                                    <td v-if="item.applicable_price">
                                        <div class="text-right">
                                            <strong>{{
                                                formatCurrency(
                                                    item.applicable_price.price_list_rate
                                                )
                                            }}</strong>
                                        </div>
                                        <div class="valid-range-text">
                                            {{ formatDate(item.applicable_price.valid_from) }}
                                            <span v-if="item.applicable_price.valid_upto">
                                                {{ formatDate(item.applicable_price.valid_upto) }}
                                            </span>
                                        </div>
                                    </td>
                                    <td v-else colspan="2" class="text-extra-muted text-center">
                                        {{ __("No applicable price found") }}
                                    </td>

                                    <td v-if="item.applicable_price">
                                        {{
                                            item.markup !== null && item.markup !== undefined
                                                ? item.markup + " %"
                                                : " - - "
                                        }}
                                    </td>
                                    <td class="text-center">{{ item.rate }}</td>
                                    <td class="text-center">
                                        <button
                                            class="btn btn-sm btn-default add-price-btn"
                                            @click="openNewPriceDialog(item)"
                                            :title="__('Add Price')"
                                        >
                                            <i class="fa fa-plus"></i>
                                        </button>
                                        <button
                                            v-if="item.applicable_price"
                                            class="btn btn-sm btn-default edit-price-btn"
                                            @click="openEditPriceDialog(item)"
                                            :title="__('Edit')"
                                        >
                                            <i class="fa fa-pencil"></i>
                                        </button>
                                        <button
                                            v-if="item.applicable_price"
                                            class="btn btn-sm btn-default delete-price-btn"
                                            @click="askToDeletePrice(item.applicable_price.name)"
                                            :title="__('Delete')"
                                        >
                                            <i class="fa fa-trash"></i>
                                        </button>
                                        <button
                                            class="btn btn-sm btn-default calculator-btn"
                                            @click="toggleMarkupCalculator(item.item_code)"
                                            :title="__('Calculate Markup')"
                                        >
                                            <i class="fa fa-calculator"></i>
                                        </button>
                                    </td>
                                </tr>
                                <tr
                                    v-if="expandedItem === item.item_code"
                                    class="markup-calculator-row"
                                >
                                    <td colspan="5">
                                        <div>
                                            <!--  class="markup-calculator-container"> -->
                                            <!-- <div class="calculator-title">{{ __("Markup Calculator") }} - {{ item.item_code }}</div> -->
                                            <!-- <div class="calculator-inputs"></div> -->
                                            <div class="markup-cheatsheet">
                                                <div
                                                    class="cheatsheet-title flex justify-between items-center"
                                                >
                                                    <span>
                                                        {{ __("Suggested Prices") }}
                                                    </span>
                                                    <div class="buttons">
                                                        <button
                                                            v-if="item.applicable_price"
                                                            class="btn btn-secondary-dark btn-sm rounded"
                                                            @click="openEditPriceDialog(item)"
                                                        >
                                                            {{ __("Enter Custom Price") }}
                                                        </button>
                                                        <button
                                                            class="btn btn-secondary btn-sm rounded"
                                                            @click="closeCalculator"
                                                        >
                                                            {{ __("Collapse") }}
                                                        </button>
                                                    </div>
                                                </div>
                                                <div class="cheatsheet-grid">
                                                    <div
                                                        v-for="option in getUniqueMarkupOptions(
                                                            item
                                                        )"
                                                        :key="option.markup"
                                                        class="markup-option"
                                                    >
                                                        <div class="calculated-price">
                                                            {{ formatCurrency(option.price) }}
                                                        </div>
                                                        <button
                                                            class="btn btn-success btn-sm rounded"
                                                            @click="
                                                                applySuggestedPrice(
                                                                    item,
                                                                    option.price,
                                                                    item.applicable_price
                                                                        ? item.applicable_price
                                                                              .name
                                                                        : null
                                                                )
                                                            "
                                                        >
                                                            <span v-if="item.applicable_price">{{
                                                                __("Apply")
                                                            }}</span>
                                                            <span v-else>{{ __("Set") }}</span>
                                                            ({{ option.markup }}%)
                                                        </button>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    </td>
                                </tr>
                            </template>
                        </tbody>
                    </table>
                    <div class="multi-price-note mt-3">
                        <strong class="multiple-prices-indicator">*</strong>
                        {{ __("Indicates item has multiple prices") }}
                    </div>
                </div>
            </div>
            <div class="modal-footer">
                <button type="button" class="btn btn-secondary" @click="closeModal">
                    {{ __("Close") }}
                </button>
            </div>
        </div>
    </div>
</template>

<script>
export default {
    name: "ItemPricesModal",
    props: {
        isOpen: Boolean,
        invoiceName: String,
        frm: Object,
        forced: Boolean,
    },
    emits: ["close", "reopen"],
    data() {
        return {
            itemsData: [],
            loading: true,
            expandedItem: null,
            markupCalculatorData: {
                customPrice: null,
            },
        };
    },
    watch: {
        isOpen(newVal) {
            if (newVal) {
                this.fetchItemPrices();
            }
        },
    },
    mounted() {
        if (this.isOpen) {
            this.fetchItemPrices();
        }
    },
    methods: {
        getUniqueMarkupOptions(item) {
            const options = [];
            const seenPrices = new Set();

            // Try base markups first
            let markup = 20;
            while (options.length < 5) {
                const price = this.calculateWithMarkup(item.rate, markup, item.vat_rate);
                // console.log("Calculated price for markup", markup, "is", price, "when rate is", item.rate, "and vat is", item.vat_rate);
                const priceKey = price.toFixed(2);

                if (!seenPrices.has(priceKey)) {
                    seenPrices.add(priceKey);
                    options.push({
                        markup: this.getMarkup(priceKey, item.vat_rate, item.rate),
                        price: priceKey,
                    });
                }

                markup += 2.5;
            }

            return options;
        },
        fetchItemPrices() {
            this.loading = true;
            frappe.call({
                method: "lithuania_compliance.api.purchase_invoice.get_item_prices",
                args: {
                    invoice_name: this.invoiceName,
                },
                callback: (r) => {
                    if (r.message) {
                        let items_data = r.message;

                        // Filter items if not forced
                        if (!this.forced) {
                            items_data = (r.message || []).filter((item) => {
                                // Really specific for Lithuania
                                if (item.item_name === "Užstatinė tara") {
                                    return false;
                                }
                                const has_no_price = !item.applicable_price;
                                const markup_value =
                                    typeof item.markup === "number" ? item.markup : null;
                                const has_low_markup = markup_value !== null && markup_value < 20;
                                return has_no_price || has_low_markup;
                            });
                        }

                        this.itemsData = items_data;
                    }
                    this.loading = false;
                },
            });
        },
        refreshData() {
            this.fetchItemPrices();
        },
        closeModal() {
            this.$emit("close");
        },
        getMarkupClass(markup_percent, hasApplicablePrice) {
            if (!hasApplicablePrice || markup_percent === null || markup_percent === undefined) {
                return "";
            }
            if (markup_percent < 10) {
                return "markup-low";
            }
            if (markup_percent < 16) {
                return "markup-medium";
            }
            if (markup_percent < 19) {
                return "markup-near-target";
            }
            return "";
        },
        getMarkup(price, vat, buying_rate) {
            if (!price || !buying_rate) return null;
            if (vat === null || vat === undefined) vat = 0;
            const price_excl_vat = price / (1 + vat / 100);
            const markup = ((price_excl_vat - buying_rate) / buying_rate) * 100;
            return Math.round(markup * 10) / 10;
        },
        hasMultiplePrices(item) {
            return (item.other_valid_prices?.length || 0) > 0;
        },
        formatCurrency(value) {
            // Format currency value without HTML wrapper
            if (value == null) return "";
            const formatted = frappe.format(value, { fieldtype: "Currency" });
            // Remove HTML tags if present
            const tempDiv = document.createElement("div");
            tempDiv.innerHTML = formatted;
            return tempDiv.textContent || tempDiv.innerText || formatted;
        },
        formatDate(dateStr) {
            return frappe.datetime.str_to_user(dateStr);
        },
        navigateToItem(itemCode) {
            this.$emit("close");
            frappe.set_route("Form", "Item", itemCode);
        },
        editPriceDirectly(priceId) {
            this.$emit("close");
            frappe.set_route("Form", "Item Price", priceId);
        },
        askToDeletePrice(priceId) {
            frappe.confirm(__("Are you sure you want to delete this record?"), () =>
                this.deletePrice(priceId)
            );
        },
        async deletePrice(priceId) {
            this.loading = true;
            await frappe.db.delete_doc("Item Price", priceId).then(() => {
                frappe.show_alert({
                    message: __("Price deleted successfully"),
                    indicator: "green",
                });
            });
            this.loading = false;
            this.refreshData();
        },
        toggleMarkupCalculator(itemCode) {
            this.expandedItem = this.expandedItem === itemCode ? null : itemCode;
            this.markupCalculatorData.customPrice = null;
        },
        closeCalculator() {
            this.expandedItem = null;
            this.markupCalculatorData.customPrice = null;
        },
        calculateWithMarkup(basePrice, markupPercent, vat = 0) {
            if (!basePrice || basePrice <= 0) return 0;
            return this.roundToEndingNumber(
                basePrice * (1 + vat / 100) * (1 + markupPercent / 100)
            );
        },
        roundToEndingNumber(value) {
            const cents = Math.round(value * 100);
            const lastDigit = cents % 10;
            let roundedLast;

            if (lastDigit <= 2) {
                roundedLast = 0;
            } else if (lastDigit <= 7) {
                roundedLast = 5;
            } else {
                roundedLast = 9;
            }

            const roundedCents = cents - lastDigit + roundedLast;
            return roundedCents / 100;
        },
        applySuggestedPrice(item, suggestedPrice, itemPriceName) {
            if (itemPriceName) {
                this.saveItemPrice(itemPriceName, {
                    price_list_rate: suggestedPrice,
                    valid_from: frappe.datetime.get_today(),
                }).then(() => {
                    frappe.show_alert({
                        message: __("Price updated successfully"),
                        indicator: "green",
                    });
                    this.expandedItem = null;
                    this.refreshData();
                });
            } else {
                this.openNewPriceDialog(item, suggestedPrice);
            }
        },
        openNewPriceDialog(item, prefilledPrice) {
            this.expandedItem = null;
            this.markupCalculatorData.customPrice = null;

            if (!item || !item.item_code) {
                frappe.msgprint(__("Invalid item data."));
                return;
            }

            let new_dialog = new frappe.ui.Dialog({
                title: __("Add New Item Price"),
                fields: [
                    {
                        label: __("Item Name"),
                        fieldname: "item_name",
                        fieldtype: "Data",
                        read_only: 1,
                        disabled: 1,
                    },
                    {
                        label: __("Price List"),
                        fieldname: "price_list",
                        fieldtype: "Link",
                        options: "Price List",
                        reqd: 1,
                        filters: { selling: 1 },
                    },
                    {
                        label: __("Price"),
                        fieldname: "price_list_rate",
                        fieldtype: "Currency",
                        reqd: 1,
                    },
                    {
                        label: __("Valid From"),
                        fieldname: "valid_from",
                        fieldtype: "Date",
                        reqd: 1,
                    },
                    { label: __("Valid Until"), fieldname: "valid_upto", fieldtype: "Date" },
                ],
                primary_action_label: __("Save"),
                primary_action: () => {
                    let values = new_dialog.get_values();
                    if (!values) return;
                    frappe.show_alert({ message: __("Saving..."), indicator: "blue" });
                    frappe.call({
                        method: "frappe.client.insert",
                        args: {
                            doc: {
                                doctype: "Item Price",
                                item_code: item.item_code,
                                price_list_rate: values.price_list_rate,
                                price_list: values.price_list,
                                selling: 1,
                                valid_from: values.valid_from,
                                valid_upto: values.valid_upto || null,
                                currency: frappe.defaults.get_default("Currency"),
                            },
                        },
                        callback: () => {
                            frappe.show_alert({
                                message: __("Price created successfully"),
                                indicator: "green",
                            });
                            new_dialog.hide();
                            this.refreshData();
                        },
                    });
                },
            });

            new_dialog.set_values({
                item_name: item.item_name,
                item_code: item.item_code,
                price_list_rate: prefilledPrice,
                valid_from: frappe.datetime.get_today(),
            });

            new_dialog.show();

            // Auto-select the first price list option after dialog opens
            frappe.call({
                method: "frappe.client.get_list",
                args: {
                    doctype: "Price List",
                    filters: { selling: 1 },
                    fields: ["name"],
                    limit_page_length: 1,
                },
                callback: (r) => {
                    if (r.message && r.message.length > 0) {
                        new_dialog.set_value("price_list", r.message[0].name);
                    }
                },
            });
        },
        saveItemPrice(priceName, values) {
            return frappe.db.set_value("Item Price", priceName, values);
        },
        openEditPriceDialog(item) {
            if (!item.applicable_price) {
                frappe.msgprint(__("No applicable price to edit."));
                return;
            }
            this.$emit("close");
            let shouldReopen = true;
            let new_dialog = new frappe.ui.Dialog({
                title: __("Edit Item Price"),
                fields: [
                    {
                        label: __("Item Name"),
                        fieldname: "item_name",
                        fieldtype: "Data",
                        read_only: 1,
                        disabled: 1,
                    },
                    {
                        label: __("Price List"),
                        fieldname: "price_list",
                        fieldtype: "Link",
                        options: "Price List",
                        reqd: 1,
                        read_only: 1,
                        disabled: 1,
                    },
                    {
                        label: __("Price"),
                        fieldname: "price_list_rate",
                        fieldtype: "Currency",
                        reqd: 1,
                    },
                    {
                        label: __("Valid From"),
                        fieldname: "valid_from",
                        fieldtype: "Date",
                        reqd: 1,
                    },
                    { label: __("Valid Until"), fieldname: "valid_upto", fieldtype: "Date" },
                ],
                secondary_action_label: __("Open Item Price"),
                secondary_action: () => {
                    shouldReopen = false;
                    this.editPriceDirectly(item.applicable_price.name).bind(this);
                },
                primary_action_label: __("Save"),
                primary_action: () => {
                    let values = new_dialog.get_values();
                    if (!values) return;

                    this.saveItemPrice(item.applicable_price.name, values).then(() => {
                        frappe.show_alert({
                            message: __("Price updated successfully"),
                            indicator: "green",
                        });
                        new_dialog.hide();
                        this.refreshData();
                    });
                },
            });

            // Reopen the modal when dialog is closed, unless secondary action was used
            new_dialog.onhide = () => {
                if (shouldReopen) {
                    this.$emit("reopen");
                }
            };

            new_dialog.set_values({
                item_name: item.item_name,
                price_list: item.applicable_price.price_list,
                price_list_rate: item.applicable_price.price_list_rate,
                valid_from: item.applicable_price.valid_from,
                valid_upto: item.applicable_price.valid_upto || null,
            });

            new_dialog.show();
        },
    },
};
</script>

<style scoped>
.item-prices-modal-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background-color: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1030;
}

.item-prices-modal-dialog {
    box-shadow: 0 2px 10px rgba(0, 0, 0, 0.3);
    max-width: 1200px;
    width: 90%;
    max-height: 90vh;
    display: flex;
    flex-direction: column;
}

.item-prices-modal-dialog .modal-header {
    flex-shrink: 0;
    border-bottom: 1px solid var(--border-color);
}

.item-prices-modal-dialog .modal-body {
    flex: 1;
    overflow-y: auto;
    overflow-x: hidden;
}

.item-prices-modal-dialog .modal-footer {
    flex-shrink: 0;
    border-top: 1px solid var(--border-color);
}

/* Pop up row */

.manage-prices-container {
    overflow-x: auto;
}

.manage-prices-container .table th,
.manage-prices-container .table td {
    vertical-align: middle;
}

.table-header-row {
    background: var(--subtle-fg);
    border-bottom: 2px solid var(--border-color);
}

.valid-range-text {
    font-size: 0.9em;
    color: var(--text-muted);
    margin-top: 2px;
    text-align: right;
}

.item-price-row {
    border-bottom: 1px solid var(--border-color);
}

.item-price-row.markup-low {
    background-color: var(--alert-bg-danger);
}

.item-price-row.markup-medium {
    background-color: var(--alert-bg-warning);
}

.item-price-row.markup-near-target {
    background-color: var(--alert-bg-info);
}

.item-code-link {
    color: var(--alert-text-info);
    text-decoration: none;
    font-weight: 700;
}

.multiple-prices-indicator {
    color: var(--alert-text-danger);
    font-weight: 700;
}

.item-name-text {
    color: var(--text-color);
    margin-top: 2px;
}

.manage-prices-container button {
    text-decoration: none;
    margin: 0 5px;
    padding: 5px 8px;
}

.markup-calculator-row {
    background-color: var(--subtle-fg);
    border-top: 2px solid var(--blue-500);
}

.markup-calculator-container {
    padding: 20px;
    background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
    border-radius: 8px;
}

.markup-cheatsheet {
    background-color: var(--card-bg);
    padding: 15px;
    border-radius: 6px;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.cheatsheet-title {
    font-size: 1em;
    font-weight: 600;
    margin-bottom: 15px;
    color: var(--heading-color);
}

.cheatsheet-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: 15px;
}

.markup-option {
    border: 1px solid var(--border-color);
    border-radius: 6px;
    padding: 12px;
    text-align: center;
    background-color: var(--subtle-fg);
    transition: all 0.3s ease;
}

.markup-option:hover {
    border-color: var(--blue-500);
    background-color: var(--bg-blue);
    box-shadow: 0 2px 8px rgba(0, 123, 255, 0.15);
}

.calculated-price {
    font-size: 1.3em;
    font-weight: 700;
    color: var(--blue-600);
    margin-bottom: 10px;
}

.markup-option .btn {
    width: 100%;
    font-size: 0.85em;
    padding: 6px 10px;
}
</style>
