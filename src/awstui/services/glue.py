from __future__ import annotations

import boto3
from botocore.exceptions import ClientError

from awstui.models import ResourceDetails, TreeNode
from awstui.plugin import AWSServicePlugin


class GluePlugin(AWSServicePlugin):
    @property
    def name(self) -> str:
        return "Glue"

    @property
    def service_name(self) -> str:
        return "glue"

    @property
    def has_flat_root(self) -> bool:
        return False

    def get_root_nodes(self, session: boto3.Session) -> list[TreeNode]:
        return [
            TreeNode(
                id="glue:category:databases",
                label="Databases",
                node_type="category",
                service="glue",
                expandable=True,
                metadata={"category": "databases"},
            ),
        ]

    def get_children(self, session: boto3.Session, node: TreeNode) -> list[TreeNode]:
        if node.metadata.get("category") == "databases":
            client = session.client("glue")
            paginator = client.get_paginator("get_databases")
            nodes: list[TreeNode] = []
            for page in paginator.paginate():
                for db in page.get("DatabaseList", []):
                    name = db["Name"]
                    nodes.append(
                        TreeNode(
                            id=f"glue:database:{name}",
                            label=name,
                            node_type="database",
                            service="glue",
                            expandable=True,
                            metadata={
                                "database_name": name,
                                "catalog_id": db.get("CatalogId", ""),
                            },
                        )
                    )
            return nodes

        if node.node_type == "database":
            client = session.client("glue")
            paginator = client.get_paginator("get_tables")
            kwargs = _get_tables_kwargs(node)
            nodes = []
            for page in paginator.paginate(**kwargs):
                for table in page.get("TableList", []):
                    name = table["Name"]
                    nodes.append(
                        TreeNode(
                            id=f"glue:table:{node.metadata['database_name']}:{name}",
                            label=name,
                            node_type="table",
                            service="glue",
                            expandable=False,
                            metadata={
                                "table_name": name,
                                "database_name": node.metadata["database_name"],
                                "catalog_id": node.metadata.get("catalog_id", ""),
                            },
                        )
                    )
            return nodes

        return []

    def get_details(self, session: boto3.Session, node: TreeNode) -> ResourceDetails:
        if node.node_type == "database":
            client = session.client("glue")
            name = node.metadata["database_name"]
            get_db_kwargs: dict = {"Name": name}
            catalog_id = node.metadata.get("catalog_id")
            if catalog_id:
                get_db_kwargs["CatalogId"] = catalog_id
            response = client.get_database(**get_db_kwargs)
            database = response.get("Database", {})
            arn = _build_database_arn(session, database)
            if arn:
                try:
                    tags_response = client.get_tags(ResourceArn=arn)
                    database["Tags"] = tags_response.get("Tags", {})
                except ClientError:
                    database["Tags"] = {}
            table_count = _count_tables(client, node)
            return ResourceDetails(
                title=f"Glue Database: {database.get('Name', name)}",
                subtitle=arn,
                summary={
                    "Name": database.get("Name", ""),
                    "Catalog ID": database.get("CatalogId", ""),
                    "Description": database.get("Description", ""),
                    "Location URI": database.get("LocationUri", ""),
                    "ARN": arn,
                    "Created": str(database.get("CreateTime", "")),
                    "Tables": str(table_count),
                },
                raw=database,
            )

        if node.node_type == "table":
            client = session.client("glue")
            get_kwargs: dict = {
                "DatabaseName": node.metadata["database_name"],
                "Name": node.metadata["table_name"],
            }
            catalog_id = node.metadata.get("catalog_id")
            if catalog_id:
                get_kwargs["CatalogId"] = catalog_id
            response = client.get_table(**get_kwargs)
            table = response.get("Table", {})
            storage = table.get("StorageDescriptor", {})
            return ResourceDetails(
                title=f"Glue Table: {table.get('Name', node.metadata['table_name'])}",
                subtitle=(
                    f"{node.metadata['database_name']}.{node.metadata['table_name']}"
                ),
                summary={
                    "Name": table.get("Name", ""),
                    "Database": table.get("DatabaseName", ""),
                    "Description": table.get("Description", ""),
                    "Type": table.get("TableType", ""),
                    "Owner": table.get("Owner", ""),
                    "Location": storage.get("Location", ""),
                    "Columns": str(len(storage.get("Columns", []))),
                    "Partition Keys": str(len(table.get("PartitionKeys", []))),
                    "Created": str(table.get("CreateTime", "")),
                    "Updated": str(table.get("UpdateTime", "")),
                },
                raw=table,
            )

        if node.node_type == "category":
            return ResourceDetails(
                title=node.label, subtitle="Expand to see resources", summary={}, raw={}
            )

        return ResourceDetails(title=node.label, subtitle="", summary={}, raw={})


def _get_tables_kwargs(database_node: TreeNode) -> dict:
    """Build get_tables kwargs from a database TreeNode."""
    kwargs: dict = {"DatabaseName": database_node.metadata["database_name"]}
    catalog_id = database_node.metadata.get("catalog_id")
    if catalog_id:
        kwargs["CatalogId"] = catalog_id
    return kwargs


def _count_tables(client, database_node: TreeNode) -> int:
    """Count tables in a Glue database by paginating get_tables."""
    paginator = client.get_paginator("get_tables")
    count = 0
    for page in paginator.paginate(**_get_tables_kwargs(database_node)):
        count += len(page.get("TableList", []))
    return count


def _build_database_arn(session: boto3.Session, database: dict) -> str:
    """Build the Glue database ARN required by get_tags.

    Glue's GetDatabase response does not include an ARN, so we construct
    one from the session's region and the database's catalog ID (which
    is the AWS account ID for the default catalog).
    """
    name = database.get("Name")
    catalog_id = database.get("CatalogId")
    region = session.region_name
    if not (name and catalog_id and region):
        return ""
    return f"arn:aws:glue:{region}:{catalog_id}:database/{name}"


plugin = GluePlugin()
