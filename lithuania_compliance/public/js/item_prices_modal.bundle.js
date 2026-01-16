import { createApp } from "vue";
import ItemPricesModal from "./ItemPricesModal.vue";

frappe.ui.ItemPricesModal = ItemPricesModal;

function setup_vue(rootComponent) {
    const app = createApp(rootComponent);

    // Make Frappe globals available to Vue components
    app.config.globalProperties.__ = window.__;
    app.config.globalProperties.frappe = window.frappe;

    return app;
}

frappe.ui.setup_vue = setup_vue;
export default setup_vue;
