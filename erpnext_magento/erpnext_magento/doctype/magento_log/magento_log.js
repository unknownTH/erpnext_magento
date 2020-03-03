frappe.ui.form.on('Magento Log', {
	refresh: function(frm) {
		frm.add_custom_button(__("Magento Settings"), function(){
			frappe.set_route("List", "Magento Settings");
		})
	}
});