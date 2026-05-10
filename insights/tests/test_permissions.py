import frappe
import frappe.share
from frappe.tests import IntegrationTestCase

from insights.api.workbooks import get_share_permissions, update_share_permissions
from insights.decorators import insights_whitelist
from insights.insights.doctype.insights_table_v3.insights_table_v3 import get_table_name
from insights.insights.doctype.insights_team.insights_team import clear_cache as clear_team_cache
from insights.permissions import PERMISSION_DOCTYPES

TEST_DS_TITLE = "Test DuckDB"
TEST_DS_NAME = frappe.scrub(TEST_DS_TITLE)
TEST_TABLE1_NAME = get_table_name(TEST_DS_NAME, "table1")
TEST_TABLE2_NAME = get_table_name(TEST_DS_NAME, "table2")
TEST_TABLE3_NAME = get_table_name(TEST_DS_NAME, "table3")


@insights_whitelist()
def protected_insights_call():
    return True


class DT:
    DATA_SOURCE = "Insights Data Source v3"
    TABLE = "Insights Table v3"
    WORKBOOK = "Insights Workbook"
    QUERY = "Insights Query v3"
    CHART = "Insights Chart v3"
    DASHBOARD = "Insights Dashboard v3"
    TEAM = "Insights Team"
    SETTINGS = "Insights Settings"


class TestInsightsPermissions(IntegrationTestCase):
    SAVEPOINT = "test_insights_permissions"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.original_enable_permissions = frappe.db.get_single_value(DT.SETTINGS, "enable_permissions")
        frappe.set_user("Administrator")
        cleanup_test_fixtures()
        create_test_users()
        clear_team_cache()
        frappe.db.commit()

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        frappe.db.set_single_value(DT.SETTINGS, "enable_permissions", cls.original_enable_permissions)
        clear_team_cache()
        cleanup_test_fixtures()
        frappe.db.commit()
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        clear_team_cache()
        frappe.db.savepoint(self.SAVEPOINT)

    def tearDown(self):
        frappe.set_user("Administrator")
        frappe.db.rollback(save_point=self.SAVEPOINT)
        clear_team_cache()
        frappe.set_user(self.original_user)
        super().tearDown()

    def toggle_team_permissions(self, enable):
        frappe.db.set_single_value(DT.SETTINGS, "enable_permissions", enable)
        clear_team_cache()

    def test_permissions_for_non_insights_user(self):
        frappe.set_user("non_insights_user@test.com")

        for doctype in PERMISSION_DOCTYPES:
            self.assertFalse(
                frappe.has_permission(doctype, ptype="read"),
                f"{doctype} should not be readable without an Insights role",
            )

        with self.assertRaises(frappe.PermissionError):
            protected_insights_call()

    def test_permissions_on_team_based_doctype_with_team_permissions_disabled(self):
        create_test_data_sources()
        create_test_tables()
        create_test_teams()
        self.toggle_team_permissions(False)

        frappe.set_user("insights_user2@test.com")
        self.assertTrue(is_allowed(DT.DATA_SOURCE, TEST_DS_NAME))
        self.assertTrue(is_allowed(DT.TABLE, TEST_TABLE1_NAME))

    def test_permission_on_team_based_doctype_with_team_permissions_enabled(self):
        create_test_data_sources()
        create_test_tables()
        team = create_test_teams()
        self.toggle_team_permissions(True)

        frappe.set_user("insights_user2@test.com")
        self.assertFalse(is_allowed(DT.DATA_SOURCE, TEST_DS_NAME))
        self.assertFalse(is_allowed(DT.TABLE, TEST_TABLE1_NAME))

        frappe.set_user("Administrator")
        team.append(
            "team_permissions",
            {"resource_type": DT.DATA_SOURCE, "resource_name": TEST_DS_NAME},
        )
        team.append(
            "team_permissions",
            {
                "resource_type": DT.TABLE,
                "resource_name": TEST_TABLE1_NAME,
            },
        )
        team.save(ignore_permissions=True)
        clear_team_cache()

        frappe.set_user("insights_user1@test.com")
        self.assertTrue(is_allowed(DT.DATA_SOURCE, TEST_DS_NAME))
        self.assertTrue(is_allowed(DT.TABLE, TEST_TABLE1_NAME))

    def test_permission_for_admin_on_team_based_doctype_with_team_permissions_enabled(
        self,
    ):
        create_test_data_sources()
        create_test_tables()
        self.toggle_team_permissions(True)

        frappe.set_user("insights_admin@test.com")
        self.assertTrue(is_allowed(DT.DATA_SOURCE, TEST_DS_NAME))
        self.assertTrue(is_allowed(DT.TABLE, TEST_TABLE1_NAME))

    def test_permission_for_workbook(self):
        workbook = create_test_workbook("insights_user1@test.com")

        frappe.set_user("insights_user1@test.com")
        self.assertTrue(is_allowed(DT.WORKBOOK, workbook.name))

        frappe.set_user("insights_user2@test.com")
        self.assertFalse(is_allowed(DT.WORKBOOK, workbook.name))

        frappe.set_user("insights_user1@test.com")
        update_share_permissions(
            workbook.name,
            [{"user": "insights_user2@test.com", "read": 1, "write": 0}],
        )
        share_permissions = get_share_permissions(workbook.name)
        self.assertIn(
            "insights_user2@test.com",
            [permission["user"] for permission in share_permissions["user_permissions"]],
        )

        frappe.set_user("insights_user2@test.com")
        self.assertTrue(is_allowed(DT.WORKBOOK, workbook.name))

        frappe.set_user("insights_user1@test.com")
        update_share_permissions(workbook.name, [])

        frappe.set_user("insights_user2@test.com")
        self.assertFalse(is_allowed(DT.WORKBOOK, workbook.name))

    def test_permission_for_dashboard(self):
        workbook = create_test_workbook("insights_user1@test.com")
        dashboard = create_test_dashboard("insights_user1@test.com", workbook.name)

        frappe.set_user("insights_user1@test.com")
        self.assertTrue(is_allowed(DT.DASHBOARD, dashboard.name))

        frappe.set_user("insights_user2@test.com")
        self.assertFalse(is_allowed(DT.DASHBOARD, dashboard.name))

        frappe.set_user("insights_user1@test.com")
        update_dashboard_access(dashboard.name, ["insights_user2@test.com"])

        frappe.set_user("insights_user2@test.com")
        self.assertTrue(is_allowed(DT.DASHBOARD, dashboard.name))

        frappe.set_user("insights_user1@test.com")
        update_dashboard_access(dashboard.name, [])

        frappe.set_user("insights_user2@test.com")
        self.assertFalse(is_allowed(DT.DASHBOARD, dashboard.name))

        frappe.set_user("insights_user1@test.com")
        update_share_permissions(
            workbook.name,
            [{"user": "insights_user2@test.com", "read": 1, "write": 0}],
        )

        frappe.set_user("insights_user2@test.com")
        self.assertTrue(is_allowed(DT.DASHBOARD, dashboard.name))
        self.assertFalse(frappe.has_permission(DT.DASHBOARD, ptype="write", doc=dashboard.name))
        with self.assertRaises(frappe.PermissionError):
            create_test_dashboard(
                "insights_user2@test.com",
                workbook.name,
                title="Permissions Test Dashboard Read Only",
            )

    def test_permission_for_chart(self):
        workbook = create_test_workbook("insights_user1@test.com")
        query = create_test_query("insights_user1@test.com", workbook.name)
        chart = create_test_chart("insights_user1@test.com", workbook.name, query.name)

        frappe.set_user("insights_user1@test.com")
        self.assertTrue(is_allowed(DT.CHART, chart.name))

        frappe.set_user("insights_user2@test.com")
        self.assertFalse(is_allowed(DT.CHART, chart.name))

        frappe.set_user("insights_user1@test.com")
        share_chart(chart.name, "insights_user2@test.com")

        frappe.set_user("insights_user2@test.com")
        self.assertTrue(is_allowed(DT.CHART, chart.name))

        frappe.set_user("insights_user1@test.com")
        unshare_chart(chart.name, "insights_user2@test.com")

        frappe.set_user("insights_user2@test.com")
        self.assertFalse(is_allowed(DT.CHART, chart.name))

        frappe.set_user("insights_user1@test.com")
        update_share_permissions(
            workbook.name,
            [{"user": "insights_user2@test.com", "read": 1, "write": 0}],
        )

        frappe.set_user("insights_user2@test.com")
        self.assertTrue(is_allowed(DT.CHART, chart.name))
        self.assertFalse(frappe.has_permission(DT.CHART, ptype="write", doc=chart.name))
        with self.assertRaises(frappe.PermissionError):
            create_test_chart(
                "insights_user2@test.com",
                workbook.name,
                query.name,
                title="Permissions Test Chart Read Only",
            )

        frappe.set_user("insights_user1@test.com")
        update_share_permissions(workbook.name, [])

        frappe.set_user("insights_user2@test.com")
        self.assertFalse(is_allowed(DT.CHART, chart.name))

        dashboard = create_test_dashboard(
            "insights_user1@test.com",
            workbook.name,
            chart.name,
            title="Permissions Test Dashboard For Chart",
        )
        frappe.set_user("insights_user1@test.com")
        update_dashboard_access(dashboard.name, ["insights_user2@test.com"])

        frappe.set_user("insights_user2@test.com")
        self.assertTrue(is_allowed(DT.CHART, chart.name))

    def test_permission_for_query(self):
        workbook = create_test_workbook("insights_user1@test.com")
        query = create_test_query("insights_user1@test.com", workbook.name)

        frappe.set_user("insights_user1@test.com")
        self.assertTrue(is_allowed(DT.QUERY, query.name))

        frappe.set_user("insights_user2@test.com")
        self.assertFalse(is_allowed(DT.QUERY, query.name))

        frappe.set_user("insights_user1@test.com")
        update_share_permissions(
            workbook.name,
            [{"user": "insights_user2@test.com", "read": 1, "write": 0}],
        )

        frappe.set_user("insights_user2@test.com")
        self.assertTrue(is_allowed(DT.QUERY, query.name))
        with self.assertRaises(frappe.PermissionError):
            create_test_query(
                "insights_user2@test.com",
                workbook.name,
                title="Permissions Test Query Read Only",
            )

        frappe.set_user("insights_user1@test.com")
        update_share_permissions(workbook.name, [])

        frappe.set_user("insights_user2@test.com")
        self.assertFalse(is_allowed(DT.QUERY, query.name))

        chart = create_test_chart(
            "insights_user1@test.com",
            workbook.name,
            query.name,
            title="Permissions Test Chart For Query",
        )
        chart = frappe.get_doc(DT.CHART, chart.name)

        frappe.set_user("insights_user2@test.com")
        self.assertFalse(is_allowed(DT.QUERY, query.name))
        self.assertFalse(is_allowed(DT.QUERY, chart.data_query))

        frappe.set_user("insights_user1@test.com")
        share_chart(chart.name, "insights_user2@test.com")

        frappe.set_user("insights_user2@test.com")
        self.assertTrue(is_allowed(DT.QUERY, query.name))
        self.assertTrue(is_allowed(DT.QUERY, chart.data_query))

        frappe.set_user("insights_user1@test.com")
        unshare_chart(chart.name, "insights_user2@test.com")

        frappe.set_user("insights_user2@test.com")
        self.assertFalse(is_allowed(DT.QUERY, query.name))
        self.assertFalse(is_allowed(DT.QUERY, chart.data_query))

        dashboard = create_test_dashboard(
            "insights_user1@test.com",
            workbook.name,
            chart.name,
            title="Permissions Test Dashboard For Query",
        )
        frappe.set_user("insights_user1@test.com")
        update_dashboard_access(dashboard.name, ["insights_user2@test.com"])

        frappe.set_user("insights_user2@test.com")
        self.assertTrue(is_allowed(DT.QUERY, query.name))
        self.assertTrue(is_allowed(DT.QUERY, chart.data_query))

        with self.assertRaises(frappe.PermissionError):
            create_test_query(
                "non_insights_user@test.com",
                workbook.name,
                title="Permissions Test Query Non Insights",
            )


def create_test_users():
    # create a website user
    user = frappe.get_doc(
        {
            "doctype": "User",
            "email": "web_user@test.com",
            "first_name": "Web",
            "last_name": "User",
            "send_welcome_email": 0,
            "user_type": "Website User",
            "enabled": 1,
        }
    ).insert()

    # create a non insights user
    user = frappe.get_doc(
        {
            "doctype": "User",
            "email": "non_insights_user@test.com",
            "first_name": "Non",
            "last_name": "Insights User",
            "send_welcome_email": 0,
            "user_type": "System User",
            "enabled": 1,
        }
    ).insert()

    # create a insights user
    user = frappe.get_doc(
        {
            "doctype": "User",
            "email": "insights_user1@test.com",
            "first_name": "Insights",
            "last_name": "User",
            "send_welcome_email": 0,
            "user_type": "System User",
            "enabled": 1,
        }
    ).insert()
    user.add_roles("Insights User")

    user = frappe.get_doc(
        {
            "doctype": "User",
            "email": "insights_user2@test.com",
            "first_name": "Insights",
            "last_name": "User",
            "send_welcome_email": 0,
            "user_type": "System User",
            "enabled": 1,
        }
    ).insert()
    user.add_roles("Insights User")

    # create a insights admin
    user = frappe.get_doc(
        {
            "doctype": "User",
            "email": "insights_admin@test.com",
            "first_name": "Insights",
            "last_name": "Admin",
            "send_welcome_email": 0,
            "user_type": "System User",
            "enabled": 1,
        }
    ).insert()
    user.add_roles("Insights Admin")


def delete_test_users():
    delete_doc_if_exists("User", "web_user@test.com")
    delete_doc_if_exists("User", "non_insights_user@test.com")
    delete_doc_if_exists("User", "insights_user1@test.com")
    delete_doc_if_exists("User", "insights_user2@test.com")
    delete_doc_if_exists("User", "insights_admin@test.com")


def create_test_data_sources():
    frappe.get_doc(
        {
            "doctype": DT.DATA_SOURCE,
            "title": TEST_DS_TITLE,
            "database_type": "DuckDB",
            "database_name": "test_duckdb",
        }
    ).insert()


def delete_test_data_sources():
    delete_doc_if_exists(DT.DATA_SOURCE, TEST_DS_NAME)


def create_test_tables():
    frappe.get_doc(
        {
            "doctype": DT.TABLE,
            "table": "table1",
            "label": "table1",
            "data_source": TEST_DS_NAME,
            "sync_mode": "Full",
        }
    ).insert()

    frappe.get_doc(
        {
            "doctype": DT.TABLE,
            "table": "table2",
            "label": "table2",
            "data_source": TEST_DS_NAME,
            "sync_mode": "Full",
        }
    ).insert()

    frappe.get_doc(
        {
            "doctype": DT.TABLE,
            "table": "table3",
            "label": "table3",
            "data_source": TEST_DS_NAME,
            "sync_mode": "Full",
        }
    ).insert()


def delete_test_tables():
    delete_doc_if_exists(DT.TABLE, TEST_TABLE1_NAME)
    delete_doc_if_exists(DT.TABLE, TEST_TABLE2_NAME)
    delete_doc_if_exists(DT.TABLE, TEST_TABLE3_NAME)


def create_test_teams():
    team1 = frappe.get_doc({"doctype": DT.TEAM, "team_name": "team1"})
    team1.append("team_members", {"user": "insights_user1@test.com"})
    team1.save()
    clear_team_cache()
    return team1


def delete_test_teams():
    delete_doc_if_exists(DT.TEAM, "team1")


def create_test_workbook(owner, title="Permissions Test Workbook"):
    frappe.set_user(owner)
    return frappe.get_doc({"doctype": DT.WORKBOOK, "title": title}).insert()


def create_test_query(owner, workbook, title="Permissions Test Query"):
    frappe.set_user(owner)
    return frappe.get_doc(
        {
            "doctype": DT.QUERY,
            "title": title,
            "workbook": workbook,
            "is_builder_query": 1,
            "use_live_connection": 1,
            "operations": [],
        }
    ).insert()


def create_test_chart(owner, workbook, query=None, title="Permissions Test Chart"):
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


def create_test_dashboard(owner, workbook, chart=None, title="Permissions Test Dashboard"):
    frappe.set_user(owner)
    items = []
    if chart:
        items.append({"id": "chart-1", "type": "chart", "chart": chart})

    dashboard = frappe.get_doc(
        {
            "doctype": DT.DASHBOARD,
            "title": title,
            "workbook": workbook,
            "items": items,
        }
    ).insert()
    return frappe.get_doc(DT.DASHBOARD, dashboard.name)


def delete_test_workbooks():
    workbooks = frappe.get_all(
        DT.WORKBOOK,
        filters={"title": ["like", "Permissions Test Workbook%"]},
        pluck="name",
    )
    for workbook in workbooks:
        frappe.delete_doc(DT.WORKBOOK, workbook, force=True)


def is_allowed(doctype, docname):
    return bool(frappe.get_list(doctype, filters={"name": docname}, pluck="name", limit=1))


def update_dashboard_access(dashboard_name, people_with_access):
    frappe.get_doc(DT.DASHBOARD, dashboard_name).update_access(
        {
            "is_public": 0,
            "is_shared_with_organization": 0,
            "people_with_access": people_with_access,
        }
    )


def share_chart(chart_name, user):
    frappe.share.add(DT.CHART, chart_name, user=user, read=1, notify=0)


def unshare_chart(chart_name, user):
    share_name = frappe.db.get_value(
        "DocShare",
        {
            "share_doctype": DT.CHART,
            "share_name": chart_name,
            "user": user,
        },
    )
    if share_name:
        frappe.delete_doc("DocShare", share_name, ignore_permissions=True)


def cleanup_test_fixtures():
    delete_test_workbooks()
    delete_test_teams()
    delete_test_tables()
    delete_test_data_sources()
    delete_test_users()
    clear_team_cache()


def delete_doc_if_exists(doctype, name):
    if frappe.db.exists(doctype, name):
        frappe.delete_doc(doctype, name, force=True)
