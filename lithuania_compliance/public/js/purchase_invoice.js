let itemPricesApp = null;
let itemPricesRootComponent = null;

frappe.ui.form.on("Purchase Invoice", {
    refresh: function (frm) {
        if (!frm.is_new() && frm.doc.docstatus === 0) {
            frm.add_custom_button(
                __("Item Prices"),
                function () {
                    getItemPricesAndOpenDialog(frm, true);
                },
                __("Preview")
            );
        } else if (!frm.is_new()) {
            frm.add_custom_button(
                __("Item Prices"),
                function () {
                    getItemPricesAndOpenDialog(frm, true);
                },
                __("View")
            );
        }
    },
});

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

function show_manage_prices_dialog(frm, forced = false) {
    // Create container for Vue app
    const modalContainer = document.createElement("div");
    modalContainer.id = "item-prices-modal-container";
    document.body.appendChild(modalContainer);

    (async () => {
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
    })();
}
