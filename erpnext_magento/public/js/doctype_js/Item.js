// Set Field Properties if Item is synced with Magento
frappe.ui.form.on("Item", {
    refresh: function(frm) {
        if(frm.doc.sync_with_magento === 1) {
            frm.set_df_property("magento_attribute_set_name", "reqd", 1);
        }
        if(frm.doc.variant_of != null) {
          frm.set_df_property("sync_with_magento", "read_only", 1);
        }
        if(frm.doc.variant_of != null) {
          frm.set_df_property("magento_attribute_set_name", "read_only", 1);
        }
        if(frm.doc.variant_of != null) {
          frm.set_df_property("magento_websites", "read_only", 1);
        }
        if(frm.doc.variant_of != null) {
          frm.set_df_property("magento_categories", "read_only", 1);
        }
        if(frm.doc.variant_of != null) {
          frm.set_df_property("magento_description", "read_only", 1);
        }
        if(frm.doc.magento_product_id != 0) {
          frm.set_df_property("magento_attribute_set_name", "unique", 1);
        }
    }
});

frappe.ui.form.on("Item", "sync_with_magento", function(frm) {
    if(frm.doc.sync_with_magento === 1) {
        frm.set_df_property("magento_attribute_set_name", "reqd", 1);
    }
    if(frm.doc.sync_with_magento === 0) {
        frm.set_df_property("magento_attribute_set_name", "reqd", 0);
    }
    if(frm.doc.magento_product_id != 0) {
      frm.set_df_property("magento_attribute_set_name", "unique", 1);
    }
});
