// Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt

frappe.provide("erpnext_magento.magento_settings");

frappe.ui.form.on("Magento Settings", "onload", function(frm, dt, dn){
	frappe.call({
		method:"erpnext_magento.erpnext_magento.doctype.magento_settings.magento_settings.get_series",
		callback:function(r){
			$.each(r.message, function(key, value){
				set_field_options(key, value)
			})
		}
	})
	erpnext_magento.magento_settings.setup_queries(frm);
})

frappe.ui.form.on("Magento Settings", "app_type", function(frm, dt, dn) {
	frm.toggle_reqd("api_key", (frm.doc.app_type == "Private"));
	frm.toggle_reqd("password", (frm.doc.app_type == "Private"));
})

frappe.ui.form.on("Magento Settings", "refresh", function(frm){
	if(!frm.doc.__islocal && frm.doc.enable_magento === 1){
		frm.toggle_reqd("price_list", true);
		frm.toggle_reqd("warehouse", true);
		frm.toggle_reqd("taxes", true);
		frm.toggle_reqd("company", true);
		frm.toggle_reqd("cost_center", true);
		frm.toggle_reqd("cash_bank_account", true);
		frm.toggle_reqd("sales_order_series", true);
		frm.toggle_reqd("customer_group", true);
		
		frm.toggle_reqd("sales_invoice_series", frm.doc.sync_sales_invoice);
		frm.toggle_reqd("delivery_note_series", frm.doc.sync_delivery_note);

		frm.add_custom_button(__('Sync Magento'), function() {
			frappe.call({
				method:"erpnext_magento.erpnext_magento.api.sync_magento",
			})
		}).addClass("btn-primary");
	}

	frm.add_custom_button(__("Magento Log"), function(){
		frappe.set_route("List", "Magento Log");
	})
	
	frm.add_custom_button(__("Reset Last Sync Date"), function(){
		var dialog = new frappe.ui.Dialog({
			title: __("Reset Last Sync Date"),
			fields: [
				{"fieldtype": "Datetime", "label": __("Date"), "fieldname": "last_sync_date", "reqd": 1 },
				{"fieldtype": "Button", "label": __("Set last sync date"), "fieldname": "set_last_sync_date", "cssClass": "btn-primary"},
			]
		});

		dialog.fields_dict.set_last_sync_date.$input.click(function() {
			args = dialog.get_values();
			if(!args) return;

			frm.set_value("last_sync_datetime", args['last_sync_date']);
			frm.save();

			dialog.hide();
		});
		dialog.show();
	})


	frappe.call({
		method: "erpnext_magento.api.get_log_status",
		callback: function(r) {
			if(r.message){
				frm.dashboard.set_headline_alert(r.message.text, r.message.alert_class)
			}
		}
	})

})


$.extend(erpnext_magento.magento_settings, {
	setup_queries: function(frm) {
		frm.fields_dict["warehouse"].get_query = function(doc) {
			return {
				filters:{
					"company": doc.company,
					"is_group": "No"
				}
			}
		}

		frm.fields_dict["taxes"].grid.get_field("tax_account").get_query = function(doc, dt, dn){
			return {
				"query": "erpnext.controllers.queries.tax_account_query",
				"filters": {
					"account_type": ["Tax", "Chargeable", "Expense Account"],
					"company": doc.company
				}
			}
		}

		frm.fields_dict["cash_bank_account"].get_query = function(doc) {
			return {
				filters: [
					["Account", "account_type", "in", ["Cash", "Bank"]],
					["Account", "root_type", "=", "Asset"],
					["Account", "is_group", "=",0],
					["Account", "company", "=", doc.company]
				]
			}
		}

		frm.fields_dict["cost_center"].get_query = function(doc) {
			return {
				filters:{
					"company": doc.company,
					"is_group": "No"
				}
			}
		}
	}
})
