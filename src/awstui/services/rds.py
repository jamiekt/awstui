from __future__ import annotations

import boto3

from awstui.models import ResourceDetails, TreeNode
from awstui.plugin import AWSServicePlugin


class RDSPlugin(AWSServicePlugin):
    @property
    def name(self) -> str:
        return "RDS"

    @property
    def service_name(self) -> str:
        return "rds"

    @property
    def has_flat_root(self) -> bool:
        return False

    def get_root_nodes(self, session: boto3.Session) -> list[TreeNode]:
        return [
            TreeNode(id="rds:category:instances", label="DB Instances", node_type="category", service="rds", expandable=True, metadata={"category": "instances"}),
            TreeNode(id="rds:category:clusters", label="DB Clusters", node_type="category", service="rds", expandable=True, metadata={"category": "clusters"}),
        ]

    def get_children(self, session: boto3.Session, node: TreeNode) -> list[TreeNode]:
        client = session.client("rds")

        if node.metadata.get("category") == "instances":
            response = client.describe_db_instances()
            return [
                TreeNode(id=f"rds:instance:{db['DBInstanceIdentifier']}", label=db["DBInstanceIdentifier"], node_type="db_instance", service="rds", expandable=False, metadata={"db_instance_id": db["DBInstanceIdentifier"]})
                for db in response.get("DBInstances", [])
            ]

        if node.metadata.get("category") == "clusters":
            response = client.describe_db_clusters()
            return [
                TreeNode(id=f"rds:cluster:{c['DBClusterIdentifier']}", label=c["DBClusterIdentifier"], node_type="db_cluster", service="rds", expandable=False, metadata={"db_cluster_id": c["DBClusterIdentifier"]})
                for c in response.get("DBClusters", [])
            ]

        return []

    def get_details(self, session: boto3.Session, node: TreeNode) -> ResourceDetails:
        client = session.client("rds")

        if node.node_type == "db_instance":
            response = client.describe_db_instances(DBInstanceIdentifier=node.metadata["db_instance_id"])
            db = response["DBInstances"][0]
            endpoint = db.get("Endpoint", {})
            return ResourceDetails(
                title=f"RDS Instance: {db['DBInstanceIdentifier']}",
                subtitle=db.get("DBInstanceArn", ""),
                summary={
                    "Identifier": db["DBInstanceIdentifier"],
                    "Class": db.get("DBInstanceClass", ""),
                    "Engine": db.get("Engine", ""),
                    "Engine Version": db.get("EngineVersion", ""),
                    "Status": db.get("DBInstanceStatus", ""),
                    "Endpoint": endpoint.get("Address", ""),
                    "Port": str(endpoint.get("Port", "")),
                    "Storage (GB)": str(db.get("AllocatedStorage", "")),
                },
                raw=db,
            )

        if node.node_type == "db_cluster":
            response = client.describe_db_clusters(DBClusterIdentifier=node.metadata["db_cluster_id"])
            cluster = response["DBClusters"][0]
            return ResourceDetails(
                title=f"RDS Cluster: {cluster['DBClusterIdentifier']}",
                subtitle=cluster.get("DBClusterArn", ""),
                summary={
                    "Identifier": cluster["DBClusterIdentifier"],
                    "Engine": cluster.get("Engine", ""),
                    "Engine Version": cluster.get("EngineVersion", ""),
                    "Status": cluster.get("Status", ""),
                    "Endpoint": cluster.get("Endpoint", ""),
                    "Reader Endpoint": cluster.get("ReaderEndpoint", ""),
                    "Members": str(len(cluster.get("DBClusterMembers", []))),
                },
                raw=cluster,
            )

        if node.node_type == "category":
            return ResourceDetails(title=node.label, subtitle="Expand to see resources", summary={}, raw={})

        return ResourceDetails(title=node.label, subtitle="", summary={}, raw={})


plugin = RDSPlugin()
