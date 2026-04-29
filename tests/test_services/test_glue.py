from unittest.mock import MagicMock

from awstui.models import TreeNode
from awstui.services.glue import GluePlugin


def make_session(region: str = "us-east-1"):
    session = MagicMock()
    session.region_name = region
    return session


def test_glue_plugin_properties():
    plugin = GluePlugin()
    assert plugin.name == "Glue"
    assert plugin.service_name == "glue"
    assert plugin.has_flat_root is False


def test_get_root_nodes_returns_databases_category():
    session = make_session()
    plugin = GluePlugin()
    nodes = plugin.get_root_nodes(session)

    assert len(nodes) == 1
    assert nodes[0].label == "Databases"
    assert nodes[0].node_type == "category"
    assert nodes[0].expandable is True


def test_get_children_of_databases_lists_databases():
    session = make_session()
    client = session.client.return_value
    client.get_paginator.return_value.paginate.return_value = [
        {
            "DatabaseList": [
                {"Name": "default", "CatalogId": "123456789012"},
                {"Name": "analytics", "CatalogId": "123456789012"},
            ]
        }
    ]

    node = TreeNode(
        id="glue:category:databases",
        label="Databases",
        node_type="category",
        service="glue",
        expandable=True,
        metadata={"category": "databases"},
    )

    plugin = GluePlugin()
    children = plugin.get_children(session, node)

    assert len(children) == 2
    assert children[0].label == "default"
    assert children[0].node_type == "database"
    # Databases are expandable — their children are Glue tables.
    assert children[0].expandable is True
    assert children[0].metadata["database_name"] == "default"
    assert children[0].metadata["catalog_id"] == "123456789012"


def test_get_children_paginates():
    session = make_session()
    client = session.client.return_value
    client.get_paginator.return_value.paginate.return_value = [
        {"DatabaseList": [{"Name": "a", "CatalogId": "123"}]},
        {"DatabaseList": [{"Name": "b", "CatalogId": "123"}]},
    ]

    node = TreeNode(
        id="glue:category:databases",
        label="Databases",
        node_type="category",
        service="glue",
        expandable=True,
        metadata={"category": "databases"},
    )

    plugin = GluePlugin()
    children = plugin.get_children(session, node)
    assert [c.label for c in children] == ["a", "b"]


def test_get_details_for_database_includes_tags_and_table_count():
    session = make_session(region="eu-west-1")
    client = session.client.return_value
    client.get_database.return_value = {
        "Database": {
            "Name": "analytics",
            "CatalogId": "123456789012",
            "Description": "Analytics warehouse",
            "LocationUri": "s3://my-bucket/analytics/",
            "CreateTime": "2026-01-01T00:00:00Z",
        }
    }
    client.get_tags.return_value = {"Tags": {"Environment": "prod"}}
    # get_tables is used both for listing children and for counting in details.
    client.get_paginator.return_value.paginate.return_value = [
        {"TableList": [{"Name": "events"}, {"Name": "users"}]},
        {"TableList": [{"Name": "sessions"}]},
    ]

    node = TreeNode(
        id="glue:database:analytics",
        label="analytics",
        node_type="database",
        service="glue",
        expandable=True,
        metadata={"database_name": "analytics", "catalog_id": "123456789012"},
    )

    plugin = GluePlugin()
    details = plugin.get_details(session, node)

    expected_arn = "arn:aws:glue:eu-west-1:123456789012:database/analytics"
    assert details.title == "Glue Database: analytics"
    assert details.subtitle == expected_arn
    assert details.summary["Name"] == "analytics"
    assert details.summary["Catalog ID"] == "123456789012"
    assert details.summary["Tables"] == "3"
    assert details.raw["Tags"] == {"Environment": "prod"}
    client.get_tags.assert_called_once_with(ResourceArn=expected_arn)
    client.get_database.assert_called_once_with(
        Name="analytics", CatalogId="123456789012"
    )


def test_get_details_for_database_without_catalog_id_skips_catalogid_arg():
    session = make_session()
    client = session.client.return_value
    client.get_database.return_value = {"Database": {"Name": "default"}}
    client.get_paginator.return_value.paginate.return_value = [{"TableList": []}]

    node = TreeNode(
        id="glue:database:default",
        label="default",
        node_type="database",
        service="glue",
        expandable=True,
        metadata={"database_name": "default"},
    )

    plugin = GluePlugin()
    details = plugin.get_details(session, node)

    client.get_database.assert_called_once_with(Name="default")
    client.get_tags.assert_not_called()
    assert details.summary["Tables"] == "0"
    assert details.title == "Glue Database: default"


def test_get_children_of_database_lists_tables():
    session = make_session()
    client = session.client.return_value
    client.get_paginator.return_value.paginate.return_value = [
        {
            "TableList": [
                {"Name": "events"},
                {"Name": "users"},
            ]
        }
    ]

    node = TreeNode(
        id="glue:database:analytics",
        label="analytics",
        node_type="database",
        service="glue",
        expandable=True,
        metadata={"database_name": "analytics", "catalog_id": "123"},
    )

    plugin = GluePlugin()
    children = plugin.get_children(session, node)

    assert len(children) == 2
    assert children[0].label == "events"
    assert children[0].node_type == "table"
    assert children[0].expandable is False
    assert children[0].metadata["table_name"] == "events"
    assert children[0].metadata["database_name"] == "analytics"
    assert children[0].metadata["catalog_id"] == "123"
    # get_tables paginator is invoked with DatabaseName + CatalogId.
    paginate_kwargs = client.get_paginator.return_value.paginate.call_args.kwargs
    assert paginate_kwargs == {"DatabaseName": "analytics", "CatalogId": "123"}


def test_get_details_for_table():
    session = make_session()
    client = session.client.return_value
    client.get_table.return_value = {
        "Table": {
            "Name": "events",
            "DatabaseName": "analytics",
            "TableType": "EXTERNAL_TABLE",
            "Description": "Page view events",
            "Owner": "analytics-team",
            "StorageDescriptor": {
                "Location": "s3://my-bucket/events/",
                "Columns": [
                    {"Name": "id", "Type": "string", "Comment": "unique event id"},
                    {"Name": "ts", "Type": "timestamp"},
                ],
            },
            "PartitionKeys": [{"Name": "dt", "Type": "date", "Comment": "event date"}],
            "CreateTime": "2026-01-01T00:00:00Z",
        }
    }

    node = TreeNode(
        id="glue:table:analytics:events",
        label="events",
        node_type="table",
        service="glue",
        expandable=False,
        metadata={
            "table_name": "events",
            "database_name": "analytics",
            "catalog_id": "123",
        },
    )

    plugin = GluePlugin()
    details = plugin.get_details(session, node)

    assert details.title == "Glue Table: events"
    assert details.subtitle == "analytics.events"
    assert details.summary["Location"] == "s3://my-bucket/events/"
    # Columns and partition keys render as their own summary groups.
    groups = dict(details.summary_groups)
    assert groups["Columns"] == {
        "id": "string — unique event id",
        "ts": "timestamp",
    }
    assert groups["Partition Keys"] == {"dt": "date — event date"}
    # Top-level summary no longer includes raw counts — those are visible
    # in the group heading.
    assert "Columns" not in details.summary
    assert "Partition Keys" not in details.summary
    client.get_table.assert_called_once_with(
        DatabaseName="analytics", Name="events", CatalogId="123"
    )


def test_get_details_for_table_without_columns_or_partitions():
    session = make_session()
    client = session.client.return_value
    client.get_table.return_value = {
        "Table": {
            "Name": "empty",
            "DatabaseName": "analytics",
            "StorageDescriptor": {"Location": "s3://x/empty/"},
        }
    }

    node = TreeNode(
        id="glue:table:analytics:empty",
        label="empty",
        node_type="table",
        service="glue",
        expandable=False,
        metadata={"table_name": "empty", "database_name": "analytics"},
    )

    plugin = GluePlugin()
    details = plugin.get_details(session, node)

    # No group when there's nothing to put in it.
    assert details.summary_groups == []


def test_get_details_for_category():
    session = make_session()
    plugin = GluePlugin()
    node = TreeNode(
        id="glue:category:databases",
        label="Databases",
        node_type="category",
        service="glue",
        expandable=True,
        metadata={"category": "databases"},
    )
    details = plugin.get_details(session, node)
    assert details.title == "Databases"
    assert details.summary == {}
