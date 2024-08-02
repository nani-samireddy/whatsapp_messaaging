app_name = "whatsapp_messaging"
app_title = "Whatsapp Messaging"
app_publisher = "nani-samireddy"
app_description = "Integrate Whatsapp messaging with frappe"
app_email = "nanisamireddy05@gmail.com"
app_license = "mit"
# required_apps = []

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/whatsapp_messaging/css/whatsapp_messaging.css"
app_include_js = ["whatsapp_messaging.bundle.js"]

# include js, css files in header of web template
# web_include_css = "/assets/whatsapp_messaging/css/whatsapp_messaging.css"
# web_include_js = "/assets/whatsapp_messaging/js/whatsapp_messaging.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "whatsapp_messaging/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "whatsapp_messaging/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "whatsapp_messaging.utils.jinja_methods",
# 	"filters": "whatsapp_messaging.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "whatsapp_messaging.install.before_install"
# after_install = "whatsapp_messaging.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "whatsapp_messaging.uninstall.before_uninstall"
# after_uninstall = "whatsapp_messaging.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "whatsapp_messaging.utils.before_app_install"
# after_app_install = "whatsapp_messaging.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "whatsapp_messaging.utils.before_app_uninstall"
# after_app_uninstall = "whatsapp_messaging.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "whatsapp_messaging.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"*": {
     	"on_update": "whatsapp_messaging.controller.ws_handle_on_update",
        "after_insert": "whatsapp_messaging.controller.ws_handle_on_create",
        "on_trash": "whatsapp_messaging.controller.ws_handle_on_trash",
        "on_submit": "whatsapp_messaging.controller.ws_handle_on_submit",
        # "on_change": "your_app.api.patient.on_change"
		# "before_insert": "whatsapp_messaging.controller.whatsapp_messaging_on_create_handler",
		# "on_change": "whatsapp_messaging.controller.whatsapp_messaging_on_update_handler",
		# "on_trash": "whatsapp_messaging.controller.whatsapp_messaging_on_delete_handler",
		# "on_update": "whatsapp_messaging.controller.whatsapp_messaging_on_update_handler",
	}
}

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"whatsapp_messaging.tasks.all"
# 	],
# 	"daily": [
# 		"whatsapp_messaging.tasks.daily"
# 	],
# 	"hourly": [
# 		"whatsapp_messaging.tasks.hourly"
# 	],
# 	"weekly": [
# 		"whatsapp_messaging.tasks.weekly"
# 	],
# 	"monthly": [
# 		"whatsapp_messaging.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "whatsapp_messaging.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "whatsapp_messaging.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "whatsapp_messaging.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["whatsapp_messaging.utils.before_request"]
# after_request = ["whatsapp_messaging.utils.after_request"]

# Job Events
# ----------
# before_job = ["whatsapp_messaging.utils.before_job"]
# after_job = ["whatsapp_messaging.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"whatsapp_messaging.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }
