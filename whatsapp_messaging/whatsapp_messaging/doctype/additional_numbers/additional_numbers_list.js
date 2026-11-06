frappe.listview_settings['Additional Numbers'] = {
    refresh(listview) {
        if (listview.can_create && !frappe.boot.read_only && !listview.checked_docnames.size) {
            listview.page.set_primary_action(__('Add number'), () => listview.make_new_doc(), 'plus');
        }
    },
};
