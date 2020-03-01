// Set Field Values if Customer Type is Individual
frappe.ui.form.on("Customer", {
    refresh: function(frm) {
      if(frm.doc.customer_type === "Individual") {
          frm.set_df_property("customer_first_name", "reqd", 1);
          frm.set_df_property("customer_last_name", "reqd", 1);
      }
    }
  });

// Update Customer Name Field on Change
frappe.ui.form.on("Customer", "customer_first_name", function(frm) { 
    if (frm.doc.customer_first_name === "") {
        frm.set_value("customer_name", strip(frm.doc.customer_first_name + " " + frm.doc.customer_last_name));
    } else {
        frm.set_value("customer_name", strip(frm.doc.customer_first_name + " " + frm.doc.customer_middle_name + " " + frm.doc.customer_last_name));
    }
});

frappe.ui.form.on("Customer", "customer_middle_name", function(frm) { 
    if (frm.doc.customer_first_name === "") {
        frm.set_value("customer_name", strip(frm.doc.customer_first_name + " " + frm.doc.customer_last_name));
    } else {
        frm.set_value("customer_name", strip(frm.doc.customer_first_name + " " + frm.doc.customer_middle_name + " " + frm.doc.customer_last_name));
    }
});

frappe.ui.form.on("Customer", "customer_last_name", function(frm) { 
    if (frm.doc.customer_first_name === "") {
        frm.set_value("customer_name", strip(frm.doc.customer_first_name + " " + frm.doc.customer_last_name));
    } else {
        frm.set_value("customer_name", strip(frm.doc.customer_first_name + " " + frm.doc.customer_middle_name + " " + frm.doc.customer_last_name));
    }
});