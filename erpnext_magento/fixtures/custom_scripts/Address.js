// Set field values if address is synced with Magento
frappe.ui.form.on("Address", {
    refresh: function(frm) {
      if(frm.doc.magento_address_id > 0) {
          frm.set_df_property("country", "reqd", 1);
          frm.set_df_property("state", "reqd", 1);
          frm.set_df_property("pincode", "reqd", 1);
      }
    }
  });
