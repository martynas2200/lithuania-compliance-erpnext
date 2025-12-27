app_name = "lithuania_compliance"
app_title = "lithuania Compliance"
app_publisher = "Martynas Miliauskas"
app_description = "Adjust ERPNext to adhere to VMI requirements"
app_email = "pagalba@ekranas.info"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

override_doctype_class = {"Purchase Invoice": "lithuania_compliance.overrides.CustomPurchaseInvoice"}

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "lithuania_compliance",
# 		"logo": "/assets/lithuania_compliance/logo.png",
# 		"title": "lithuania Compliance",
# 		"route": "/lithuania_compliance",
# 		"has_permission": "lithuania_compliance.api.permission.has_app_permission"
# 	}
# ]
fixtures = [{"dt": "Custom Field", "filters": [["name", "in", ["Supplier-business_code"]]]}]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/lithuania_compliance/css/lithuania_compliance.css"
# app_include_js = "/assets/lithuania_compliance/js/lithuania_compliance.js"

# include js, css files in header of web template
# web_include_css = "/assets/lithuania_compliance/css/lithuania_compliance.css"
# web_include_js = "/assets/lithuania_compliance/js/lithuania_compliance.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "lithuania_compliance/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
doctype_js = {"Purchase Invoice": "public/js/purchase_invoice.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "lithuania_compliance/public/icons.svg"

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

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "lithuania_compliance.utils.jinja_methods",
# 	"filters": "lithuania_compliance.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "lithuania_compliance.install.before_install"
after_install = "lithuania_compliance.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "lithuania_compliance.uninstall.before_uninstall"
# after_uninstall = "lithuania_compliance.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "lithuania_compliance.utils.before_app_install"
# after_app_install = "lithuania_compliance.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "lithuania_compliance.utils.before_app_uninstall"
# after_app_uninstall = "lithuania_compliance.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "lithuania_compliance.notifications.get_notification_config"

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

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"Purchase Invoice": {
		"on_submit": "lithuania_compliance.api.purchase_invoice.enqueue_supplier_items_sync",
	}
}

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"lithuania_compliance.tasks.all"
# 	],
# 	"daily": [
# 		"lithuania_compliance.tasks.daily"
# 	],
# 	"hourly": [
# 		"lithuania_compliance.tasks.hourly"
# 	],
# 	"weekly": [
# 		"lithuania_compliance.tasks.weekly"
# 	],
# 	"monthly": [
# 		"lithuania_compliance.tasks.monthly"
# 	],
# }

# Testing
# -------

after_migrate = ["lithuania_compliance.install.after_migrate"]

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "lithuania_compliance.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "lithuania_compliance.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "lithuania_compliance.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["lithuania_compliance.utils.before_request"]
# after_request = ["lithuania_compliance.utils.after_request"]

# Job Events
# ----------
# before_job = ["lithuania_compliance.utils.before_job"]
# after_job = ["lithuania_compliance.utils.after_job"]

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
# 	"lithuania_compliance.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }
