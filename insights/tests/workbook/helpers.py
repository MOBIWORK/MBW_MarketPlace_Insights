import frappe

from insights.insights.doctype.insights_data_source_v3.insights_data_source_v3 import db_connections


class DT:
    WORKBOOK = "Insights Workbook"
    QUERY = "Insights Query v3"
    CHART = "Insights Chart v3"
    DASHBOARD = "Insights Dashboard v3"
    USER = "User"


TEST_USER_EMAIL = "workbook_flow_user@test.com"
TEST_WORKBOOK_TITLE = "Workbook Flow Test Workbook"
TEST_QUERY_TITLE = "Workbook Flow Test Query"
TEST_CHART_TITLE = "Workbook Flow Test Chart"
TEST_DASHBOARD_TITLE = "Workbook Flow Test Dashboard"


def create_test_user(email=TEST_USER_EMAIL, role="Insights User"):
    if frappe.db.exists(DT.USER, email):
        user = frappe.get_doc(DT.USER, email)
    else:
        user = frappe.get_doc(
            {
                "doctype": DT.USER,
                "email": email,
                "first_name": "Workbook",
                "last_name": "Flow User",
                "send_welcome_email": 0,
                "user_type": "System User",
                "enabled": 1,
            }
        ).insert(ignore_permissions=True)

    if role and not frappe.db.exists("Has Role", {"parent": email, "role": role}):
        user.add_roles(role)

    return user


def delete_test_users():
    delete_doc_if_exists(DT.USER, TEST_USER_EMAIL)


def create_test_workbook(owner, title=TEST_WORKBOOK_TITLE):
    frappe.set_user(owner)
    return frappe.get_doc({"doctype": DT.WORKBOOK, "title": title}).insert()


def create_test_query(owner, workbook, title=TEST_QUERY_TITLE, operations=None):
    frappe.set_user(owner)
    return frappe.get_doc(
        {
            "doctype": DT.QUERY,
            "title": title,
            "workbook": workbook,
            "use_live_connection": 1,
            "is_builder_query": 1,
            "operations": operations
            or [
                {
                    "type": "source",
                    "table": {
                        "type": "table",
                        "data_source": "Site DB",
                        "table_name": "tabToDo",
                    },
                }
            ],
        }
    ).insert()


def create_test_chart(owner, workbook, query, title=TEST_CHART_TITLE):
    frappe.set_user(owner)
    chart = frappe.get_doc(
        {
            "doctype": DT.CHART,
            "title": title,
            "workbook": workbook,
            "query": query,
            "chart_type": "Bar",
            "config": {},
        }
    ).insert()
    return frappe.get_doc(DT.CHART, chart.name)


def create_test_dashboard(owner, workbook, chart, title=TEST_DASHBOARD_TITLE):
    frappe.set_user(owner)
    dashboard = frappe.get_doc(
        {
            "doctype": DT.DASHBOARD,
            "title": title,
            "workbook": workbook,
            "items": [{"id": "chart-1", "type": "chart", "chart": chart}],
        }
    ).insert()
    return frappe.get_doc(DT.DASHBOARD, dashboard.name)


def execute_test_query(query_name):
    query = frappe.get_doc(DT.QUERY, query_name)
    with db_connections():
        return query.execute()


def doc_exists(doctype, name):
    return bool(frappe.db.exists(doctype, name))


def is_visible(doctype, name):
    return bool(frappe.get_list(doctype, filters={"name": name}, pluck="name", limit=1))


def delete_test_workbooks():
    workbooks = frappe.get_all(
        DT.WORKBOOK,
        filters={"title": ["like", f"{TEST_WORKBOOK_TITLE}%"]},
        pluck="name",
    )
    for workbook in workbooks:
        frappe.delete_doc(DT.WORKBOOK, workbook, force=True)


def cleanup_workbook_flow_fixtures():
    delete_test_workbooks()
    delete_test_users()


def delete_doc_if_exists(doctype, name):
    if frappe.db.exists(doctype, name):
        frappe.delete_doc(doctype, name, force=True)
