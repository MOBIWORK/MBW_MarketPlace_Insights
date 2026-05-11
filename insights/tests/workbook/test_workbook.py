import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import set_request

from insights.api import get_doc as get_public_doc
from insights.api import run_doc_method as run_public_doc_method
from insights.api.workbooks import (
    create_folder,
    delete_folder,
    get_share_permissions,
    get_workbooks,
    import_workbook,
    move_item_to_folder,
    update_share_permissions,
    update_sort_orders,
)
from insights.tests.workbook.helpers import (
    DT,
    TEST_USER_EMAIL,
    create_test_chart,
    create_test_dashboard,
    create_test_query,
    create_test_user,
    create_test_workbook,
    delete_doc_if_exists,
    doc_exists,
)

COLLABORATOR_EMAIL = "workbook_flow_collaborator@test.com"


def cleanup_test_workbooks(*owners):
    workbooks = frappe.get_all(
        DT.WORKBOOK,
        filters={"owner": ["in", list(owners)]},
        pluck="name",
    )
    for workbook_name in workbooks:
        frappe.delete_doc(DT.WORKBOOK, workbook_name, force=True)


class TestWorkbook(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cleanup_test_workbooks(TEST_USER_EMAIL, COLLABORATOR_EMAIL)
        delete_doc_if_exists(DT.USER, TEST_USER_EMAIL)
        delete_doc_if_exists(DT.USER, COLLABORATOR_EMAIL)
        create_test_user(TEST_USER_EMAIL)
        create_test_user(COLLABORATOR_EMAIL)
        frappe.db.commit()

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        cleanup_test_workbooks(TEST_USER_EMAIL, COLLABORATOR_EMAIL)
        delete_doc_if_exists(DT.USER, TEST_USER_EMAIL)
        delete_doc_if_exists(DT.USER, COLLABORATOR_EMAIL)
        frappe.db.commit()
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        cleanup_test_workbooks(TEST_USER_EMAIL, COLLABORATOR_EMAIL)
        frappe.db.commit()

    def tearDown(self):
        frappe.set_user("Administrator")
        cleanup_test_workbooks(TEST_USER_EMAIL, COLLABORATOR_EMAIL)
        frappe.db.commit()
        frappe.set_user(self.original_user)
        super().tearDown()

    def get_doc(self, doctype, name):
        set_request(method="GET", path="/api/method/insights.api.get_doc")
        return get_public_doc(doctype, name)

    def run_doc_method(self, method, doc, args=None):
        set_request(method="POST", path="/api/method/insights.api.run_doc_method")
        return run_public_doc_method(method, doc, args=args)

    def get_workbook(self, name):
        workbook = self.get_doc(DT.WORKBOOK, name)
        for field in ("folders", "queries", "charts", "dashboards"):
            workbook[field] = frappe.parse_json(workbook.get(field)) or []
        return workbook

    def create_workbook_bundle(self, title, include_secondary_items=False, include_folders=False):
        workbook = create_test_workbook(TEST_USER_EMAIL, title=title)
        query = create_test_query(TEST_USER_EMAIL, workbook.name, title=f"{title} Query 1")
        chart = create_test_chart(TEST_USER_EMAIL, workbook.name, query.name, title=f"{title} Chart 1")
        dashboard = create_test_dashboard(
            TEST_USER_EMAIL,
            workbook.name,
            chart.name,
            title=f"{title} Dashboard 1",
        )

        bundle = {
            "workbook": workbook,
            "query": query,
            "chart": chart,
            "dashboard": dashboard,
            "folders": {},
        }

        if include_secondary_items:
            bundle["secondary_query"] = create_test_query(
                TEST_USER_EMAIL,
                workbook.name,
                title=f"{title} Query 2",
            )
            bundle["secondary_chart"] = create_test_chart(
                TEST_USER_EMAIL,
                workbook.name,
                bundle["secondary_query"].name,
                title=f"{title} Chart 2",
            )

        if include_folders:
            frappe.set_user(TEST_USER_EMAIL)
            bundle["folders"]["query"] = create_folder(
                workbook.name,
                f"{title} Query Folder",
                "query",
            )
            bundle["folders"]["chart"] = create_folder(
                workbook.name,
                f"{title} Chart Folder",
                "chart",
            )
            move_item_to_folder("query", query.name, bundle["folders"]["query"])
            move_item_to_folder("chart", chart.name, bundle["folders"]["chart"])

        return bundle

    def test_owner_can_build_workbook_query_chart_dashboard_flow(self):
        bundle = self.create_workbook_bundle("Workbook Flow Test Authoring")

        frappe.set_user(TEST_USER_EMAIL)
        workbook = self.get_workbook(bundle["workbook"].name)
        chart = self.get_doc(DT.CHART, bundle["chart"].name)
        dashboard = self.get_doc(DT.DASHBOARD, bundle["dashboard"].name)
        query_result = self.run_doc_method("execute", self.get_doc(DT.QUERY, bundle["query"].name))
        dashboard_items = frappe.parse_json(dashboard["items"]) or []

        self.assertEqual([row["name"] for row in workbook["queries"]], [bundle["query"].name])
        self.assertEqual([row["name"] for row in workbook["charts"]], [bundle["chart"].name])
        self.assertEqual([row["name"] for row in workbook["dashboards"]], [bundle["dashboard"].name])

        self.assertIn("sql", query_result)
        self.assertGreater(len(query_result["columns"]), 0)
        self.assertEqual(chart["query"], bundle["query"].name)
        self.assertTrue(chart["data_query"])
        self.assertTrue(doc_exists(DT.QUERY, chart["data_query"]))
        self.assertTrue(any(item.get("chart") == bundle["chart"].name for item in dashboard_items))

    def test_deleting_workbook_removes_the_user_visible_tree(self):
        bundle = self.create_workbook_bundle("Workbook Flow Test Delete")
        data_query_name = self.get_doc(DT.CHART, bundle["chart"].name)["data_query"]

        frappe.set_user("Administrator")
        frappe.delete_doc(DT.WORKBOOK, bundle["workbook"].name, force=True)

        self.assertFalse(doc_exists(DT.WORKBOOK, bundle["workbook"].name))
        self.assertFalse(doc_exists(DT.QUERY, bundle["query"].name))
        self.assertFalse(doc_exists(DT.CHART, bundle["chart"].name))
        self.assertFalse(doc_exists(DT.QUERY, data_query_name))
        self.assertFalse(doc_exists(DT.DASHBOARD, bundle["dashboard"].name))

    def test_owner_can_organize_and_reorder_workbook_contents(self):
        bundle = self.create_workbook_bundle(
            "Workbook Flow Test Organization",
            include_secondary_items=True,
        )

        frappe.set_user(TEST_USER_EMAIL)
        query_folder = create_folder(
            bundle["workbook"].name,
            "Workbook Flow Test Organization Query Folder",
            "query",
        )
        chart_folder = create_folder(
            bundle["workbook"].name,
            "Workbook Flow Test Organization Chart Folder",
            "chart",
        )
        move_item_to_folder("query", bundle["query"].name, query_folder)
        move_item_to_folder("chart", bundle["chart"].name, chart_folder)
        update_sort_orders(
            bundle["workbook"].name,
            [
                {"type": "folder", "name": chart_folder, "sort_order": 0},
                {"type": "folder", "name": query_folder, "sort_order": 1},
                {
                    "type": "query",
                    "name": bundle["secondary_query"].name,
                    "sort_order": 0,
                    "folder": None,
                },
                {
                    "type": "query",
                    "name": bundle["query"].name,
                    "sort_order": 1,
                    "folder": query_folder,
                },
                {
                    "type": "chart",
                    "name": bundle["secondary_chart"].name,
                    "sort_order": 0,
                    "folder": None,
                },
                {
                    "type": "chart",
                    "name": bundle["chart"].name,
                    "sort_order": 1,
                    "folder": chart_folder,
                },
            ],
        )

        workbook = self.get_workbook(bundle["workbook"].name)

        self.assertEqual([row["name"] for row in workbook["folders"]], [chart_folder, query_folder])
        self.assertEqual(
            [row["name"] for row in workbook["queries"]],
            [bundle["secondary_query"].name, bundle["query"].name],
        )
        self.assertEqual(
            [row["name"] for row in workbook["charts"]],
            [bundle["secondary_chart"].name, bundle["chart"].name],
        )
        self.assertEqual(workbook["queries"][1]["folder"], query_folder)
        self.assertEqual(workbook["charts"][1]["folder"], chart_folder)

        delete_folder(query_folder, move_items_to_root=True)
        delete_folder(chart_folder, move_items_to_root=True)

        workbook = self.get_workbook(bundle["workbook"].name)

        self.assertEqual(workbook["folders"], [])
        self.assertTrue(all(not row["folder"] for row in workbook["queries"]))
        self.assertTrue(all(not row["folder"] for row in workbook["charts"]))

    def test_duplicate_workbook_preserves_a_usable_copy(self):
        bundle = self.create_workbook_bundle(
            "Workbook Flow Test Duplicate",
            include_folders=True,
        )

        frappe.set_user(TEST_USER_EMAIL)
        original_workbook = self.get_workbook(bundle["workbook"].name)
        original_chart = self.get_doc(DT.CHART, bundle["chart"].name)
        duplicate_name = self.run_doc_method(
            "duplicate",
            self.get_doc(DT.WORKBOOK, bundle["workbook"].name),
        )
        duplicate_workbook = self.get_workbook(duplicate_name)
        duplicate_query_name = duplicate_workbook["queries"][0]["name"]
        duplicate_chart_name = duplicate_workbook["charts"][0]["name"]
        duplicate_chart = self.get_doc(DT.CHART, duplicate_chart_name)
        duplicate_dashboard = self.get_doc(
            DT.DASHBOARD,
            duplicate_workbook["dashboards"][0]["name"],
        )
        duplicate_dashboard_items = frappe.parse_json(duplicate_dashboard["items"]) or []
        duplicate_result = self.run_doc_method("execute", self.get_doc(DT.QUERY, duplicate_query_name))

        self.assertEqual(len(duplicate_workbook["folders"]), 2)
        self.assertEqual(len(duplicate_workbook["queries"]), 1)
        self.assertEqual(len(duplicate_workbook["charts"]), 1)
        self.assertEqual(len(duplicate_workbook["dashboards"]), 1)
        self.assertNotEqual(duplicate_query_name, bundle["query"].name)
        self.assertEqual(duplicate_chart["query"], duplicate_query_name)
        self.assertTrue(duplicate_chart["data_query"])
        self.assertNotEqual(duplicate_chart["data_query"], original_chart["data_query"])
        self.assertTrue(any(item.get("chart") == duplicate_chart_name for item in duplicate_dashboard_items))
        self.assertTrue(
            {row["name"] for row in duplicate_workbook["folders"]}.isdisjoint(
                {row["name"] for row in original_workbook["folders"]}
            )
        )
        self.assertIn(
            duplicate_workbook["queries"][0]["folder"], {row["name"] for row in duplicate_workbook["folders"]}
        )
        self.assertIn(
            duplicate_workbook["charts"][0]["folder"], {row["name"] for row in duplicate_workbook["folders"]}
        )
        self.assertGreater(len(duplicate_result["columns"]), 0)

    def test_export_and_import_preserve_a_usable_workflow(self):
        bundle = self.create_workbook_bundle(
            "Workbook Flow Test Import",
            include_folders=True,
        )

        frappe.set_user(TEST_USER_EMAIL)
        original_workbook = self.get_workbook(bundle["workbook"].name)
        original_chart = self.get_doc(DT.CHART, bundle["chart"].name)
        exported_workbook = self.run_doc_method(
            "export",
            self.get_doc(DT.WORKBOOK, bundle["workbook"].name),
        )
        imported_name = import_workbook(exported_workbook)
        imported_workbook = self.get_workbook(imported_name)
        imported_query_name = imported_workbook["queries"][0]["name"]
        imported_chart_name = imported_workbook["charts"][0]["name"]
        imported_chart = self.get_doc(DT.CHART, imported_chart_name)
        imported_dashboard = self.get_doc(
            DT.DASHBOARD,
            imported_workbook["dashboards"][0]["name"],
        )
        imported_dashboard_items = frappe.parse_json(imported_dashboard["items"]) or []
        imported_result = self.run_doc_method("execute", self.get_doc(DT.QUERY, imported_query_name))

        self.assertEqual(len(imported_workbook["folders"]), 2)
        self.assertEqual(len(imported_workbook["queries"]), 1)
        self.assertEqual(len(imported_workbook["charts"]), 1)
        self.assertEqual(len(imported_workbook["dashboards"]), 1)
        self.assertNotEqual(imported_query_name, bundle["query"].name)
        self.assertEqual(imported_chart["query"], imported_query_name)
        self.assertTrue(imported_chart["data_query"])
        self.assertNotEqual(imported_chart["data_query"], original_chart["data_query"])
        self.assertTrue(any(item.get("chart") == imported_chart_name for item in imported_dashboard_items))
        self.assertTrue(
            {row["name"] for row in imported_workbook["folders"]}.isdisjoint(
                {row["name"] for row in original_workbook["folders"]}
            )
        )
        self.assertIn(
            imported_workbook["queries"][0]["folder"], {row["name"] for row in imported_workbook["folders"]}
        )
        self.assertIn(
            imported_workbook["charts"][0]["folder"], {row["name"] for row in imported_workbook["folders"]}
        )
        self.assertGreater(len(imported_result["columns"]), 0)

    def test_shared_workbook_supports_read_only_public_access_but_blocks_structure_changes(self):
        bundle = self.create_workbook_bundle("Workbook Flow Test Shared")

        frappe.set_user(TEST_USER_EMAIL)
        self.run_doc_method("track_view", self.get_doc(DT.WORKBOOK, bundle["workbook"].name))
        update_share_permissions(bundle["workbook"].name, [], organization_access="view")
        share_permissions = get_share_permissions(bundle["workbook"].name)
        owner_workbooks = get_workbooks(search_term="Workbook Flow Test Shared")

        self.assertEqual(share_permissions["organization_access"], "view")
        self.assertEqual(
            {permission["user"] for permission in share_permissions["user_permissions"]},
            {TEST_USER_EMAIL},
        )
        self.assertEqual(len(owner_workbooks), 1)
        self.assertEqual(owner_workbooks[0]["name"], bundle["workbook"].name)
        self.assertEqual(owner_workbooks[0]["views"], 1)
        self.assertTrue(owner_workbooks[0]["shared_with_organization"])

        frappe.set_user(COLLABORATOR_EMAIL)
        collaborator_workbooks = get_workbooks(search_term="Workbook Flow Test Shared")
        workbook = self.get_workbook(bundle["workbook"].name)
        query = self.get_doc(DT.QUERY, bundle["query"].name)
        chart = self.get_doc(DT.CHART, bundle["chart"].name)
        dashboard = self.get_doc(DT.DASHBOARD, bundle["dashboard"].name)

        self.assertEqual([row["name"] for row in collaborator_workbooks], [bundle["workbook"].name])
        self.assertTrue(workbook["read_only"])
        self.assertTrue(query["read_only"])
        self.assertTrue(chart["read_only"])
        self.assertTrue(dashboard["read_only"])
        self.assertEqual([row["name"] for row in workbook["queries"]], [bundle["query"].name])
        self.assertEqual([row["name"] for row in workbook["charts"]], [bundle["chart"].name])
        self.assertEqual([row["name"] for row in workbook["dashboards"]], [bundle["dashboard"].name])

        with self.assertRaises(frappe.PermissionError):
            create_folder(bundle["workbook"].name, "Blocked Query Folder", "query")

        with self.assertRaises(frappe.PermissionError):
            update_sort_orders(
                bundle["workbook"].name,
                [
                    {
                        "type": "query",
                        "name": bundle["query"].name,
                        "sort_order": 0,
                        "folder": None,
                    }
                ],
            )
