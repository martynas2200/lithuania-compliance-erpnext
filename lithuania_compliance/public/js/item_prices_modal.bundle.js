import { createApp, h, reactive } from "vue";
import ItemPricesModal from "./ItemPricesModal.vue";

function mount_item_prices_modal(container, invoiceName) {
    const state = reactive({ isOpen: true, invoiceName });

    const app = createApp({
        render() {
            return h(ItemPricesModal, {
                isOpen: state.isOpen,
                invoiceName: state.invoiceName,
                onClose: () => {
                    state.isOpen = false;
                },
                onReopen: () => {
                    state.isOpen = true;
                },
            });
        },
    });

    // Make Frappe globals available to Vue components
    app.config.globalProperties.__ = window.__;
    app.config.globalProperties.frappe = window.frappe;

    app.mount(container);

    return { app, state };
}

frappe.ui.mount_item_prices_modal = mount_item_prices_modal;

export default mount_item_prices_modal;
