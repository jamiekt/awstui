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
            TreeNode(
                id="rds:category:instances",
                label="DB Instances",
                node_type="category",
                service="rds",
                expandable=True,
                metadata={"category": "instances"},
            ),
            TreeNode(
                id="rds:category:clusters",
                label="DB Clusters",
                node_type="category",
                service="rds",
                expandable=True,
                metadata={"category": "clusters"},
            ),
            TreeNode(
                id="rds:category:subnet_groups",
                label="Subnet Groups",
                node_type="category",
                service="rds",
                expandable=True,
                metadata={"category": "subnet_groups"},
            ),
            TreeNode(
                id="rds:category:parameter_groups",
                label="Parameter Groups",
                node_type="category",
                service="rds",
                expandable=True,
                metadata={"category": "parameter_groups"},
            ),
            TreeNode(
                id="rds:category:option_groups",
                label="Option Groups",
                node_type="category",
                service="rds",
                expandable=True,
                metadata={"category": "option_groups"},
            ),
            TreeNode(
                id="rds:category:snapshots",
                label="Snapshots",
                node_type="category",
                service="rds",
                expandable=True,
                metadata={"category": "snapshots"},
            ),
        ]

    def get_children(self, session: boto3.Session, node: TreeNode) -> list[TreeNode]:
        client = session.client("rds")

        if node.metadata.get("category") == "instances":
            response = client.describe_db_instances()
            return [
                TreeNode(
                    id=f"rds:instance:{db['DBInstanceIdentifier']}",
                    label=db["DBInstanceIdentifier"],
                    node_type="db_instance",
                    service="rds",
                    expandable=False,
                    metadata={"db_instance_id": db["DBInstanceIdentifier"]},
                )
                for db in response.get("DBInstances", [])
            ]

        if node.metadata.get("category") == "clusters":
            response = client.describe_db_clusters()
            return [
                TreeNode(
                    id=f"rds:cluster:{c['DBClusterIdentifier']}",
                    label=c["DBClusterIdentifier"],
                    node_type="db_cluster",
                    service="rds",
                    expandable=False,
                    metadata={"db_cluster_id": c["DBClusterIdentifier"]},
                )
                for c in response.get("DBClusters", [])
            ]

        if node.metadata.get("category") == "subnet_groups":
            response = client.describe_db_subnet_groups()
            return [
                TreeNode(
                    id=f"rds:subnet_group:{g['DBSubnetGroupName']}",
                    label=g["DBSubnetGroupName"],
                    node_type="db_subnet_group",
                    service="rds",
                    expandable=False,
                    metadata={"db_subnet_group_name": g["DBSubnetGroupName"]},
                )
                for g in response.get("DBSubnetGroups", [])
            ]

        if node.metadata.get("category") == "parameter_groups":
            return [
                TreeNode(
                    id="rds:category:db_parameter_groups",
                    label="DB Parameter Groups",
                    node_type="category",
                    service="rds",
                    expandable=True,
                    metadata={"category": "db_parameter_groups"},
                ),
                TreeNode(
                    id="rds:category:db_cluster_parameter_groups",
                    label="DB Cluster Parameter Groups",
                    node_type="category",
                    service="rds",
                    expandable=True,
                    metadata={"category": "db_cluster_parameter_groups"},
                ),
            ]

        if node.metadata.get("category") == "db_parameter_groups":
            response = client.describe_db_parameter_groups()
            return [
                TreeNode(
                    id=f"rds:db_parameter_group:{g['DBParameterGroupName']}",
                    label=g["DBParameterGroupName"],
                    node_type="db_parameter_group",
                    service="rds",
                    expandable=False,
                    metadata={"db_parameter_group_name": g["DBParameterGroupName"]},
                )
                for g in response.get("DBParameterGroups", [])
            ]

        if node.metadata.get("category") == "db_cluster_parameter_groups":
            response = client.describe_db_cluster_parameter_groups()
            return [
                TreeNode(
                    id=f"rds:db_cluster_parameter_group:{g['DBClusterParameterGroupName']}",
                    label=g["DBClusterParameterGroupName"],
                    node_type="db_cluster_parameter_group",
                    service="rds",
                    expandable=False,
                    metadata={
                        "db_cluster_parameter_group_name": g[
                            "DBClusterParameterGroupName"
                        ]
                    },
                )
                for g in response.get("DBClusterParameterGroups", [])
            ]

        if node.metadata.get("category") == "option_groups":
            response = client.describe_option_groups()
            return [
                TreeNode(
                    id=f"rds:option_group:{g['OptionGroupName']}",
                    label=g["OptionGroupName"],
                    node_type="option_group",
                    service="rds",
                    expandable=False,
                    metadata={"option_group_name": g["OptionGroupName"]},
                )
                for g in response.get("OptionGroupsList", [])
            ]

        if node.metadata.get("category") == "snapshots":
            return [
                TreeNode(
                    id="rds:category:db_snapshots",
                    label="DB Snapshots",
                    node_type="category",
                    service="rds",
                    expandable=True,
                    metadata={"category": "db_snapshots"},
                ),
                TreeNode(
                    id="rds:category:db_cluster_snapshots",
                    label="DB Cluster Snapshots",
                    node_type="category",
                    service="rds",
                    expandable=True,
                    metadata={"category": "db_cluster_snapshots"},
                ),
            ]

        if node.metadata.get("category") == "db_snapshots":
            response = client.describe_db_snapshots()
            return [
                TreeNode(
                    id=f"rds:db_snapshot:{s['DBSnapshotIdentifier']}",
                    label=s["DBSnapshotIdentifier"],
                    node_type="db_snapshot",
                    service="rds",
                    expandable=False,
                    metadata={"db_snapshot_id": s["DBSnapshotIdentifier"]},
                )
                for s in response.get("DBSnapshots", [])
            ]

        if node.metadata.get("category") == "db_cluster_snapshots":
            response = client.describe_db_cluster_snapshots()
            return [
                TreeNode(
                    id=f"rds:db_cluster_snapshot:{s['DBClusterSnapshotIdentifier']}",
                    label=s["DBClusterSnapshotIdentifier"],
                    node_type="db_cluster_snapshot",
                    service="rds",
                    expandable=False,
                    metadata={
                        "db_cluster_snapshot_id": s["DBClusterSnapshotIdentifier"]
                    },
                )
                for s in response.get("DBClusterSnapshots", [])
            ]

        return []

    def get_details(self, session: boto3.Session, node: TreeNode) -> ResourceDetails:
        client = session.client("rds")

        if node.node_type == "db_instance":
            response = client.describe_db_instances(
                DBInstanceIdentifier=node.metadata["db_instance_id"]
            )
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
            response = client.describe_db_clusters(
                DBClusterIdentifier=node.metadata["db_cluster_id"]
            )
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

        if node.node_type == "db_subnet_group":
            response = client.describe_db_subnet_groups(
                DBSubnetGroupName=node.metadata["db_subnet_group_name"]
            )
            group = response["DBSubnetGroups"][0]
            arn = group.get("DBSubnetGroupArn", "")
            if arn:
                tags_response = client.list_tags_for_resource(ResourceName=arn)
                group["TagList"] = tags_response.get("TagList", [])
            subnets = group.get("Subnets", [])
            return ResourceDetails(
                title=f"RDS Subnet Group: {group['DBSubnetGroupName']}",
                subtitle=arn,
                summary={
                    "Name": group.get("DBSubnetGroupName", ""),
                    "Description": group.get("DBSubnetGroupDescription", ""),
                    "VPC": group.get("VpcId", ""),
                    "Status": group.get("SubnetGroupStatus", ""),
                    "Subnets": str(len(subnets)),
                },
                raw=group,
            )

        if node.node_type == "db_parameter_group":
            response = client.describe_db_parameter_groups(
                DBParameterGroupName=node.metadata["db_parameter_group_name"]
            )
            group = response["DBParameterGroups"][0]
            arn = group.get("DBParameterGroupArn", "")
            if arn:
                tags_response = client.list_tags_for_resource(ResourceName=arn)
                group["TagList"] = tags_response.get("TagList", [])
            return ResourceDetails(
                title=f"RDS DB Parameter Group: {group['DBParameterGroupName']}",
                subtitle=arn,
                summary={
                    "Name": group.get("DBParameterGroupName", ""),
                    "Family": group.get("DBParameterGroupFamily", ""),
                    "Description": group.get("Description", ""),
                },
                raw=group,
            )

        if node.node_type == "db_cluster_parameter_group":
            response = client.describe_db_cluster_parameter_groups(
                DBClusterParameterGroupName=node.metadata[
                    "db_cluster_parameter_group_name"
                ]
            )
            group = response["DBClusterParameterGroups"][0]
            arn = group.get("DBClusterParameterGroupArn", "")
            if arn:
                tags_response = client.list_tags_for_resource(ResourceName=arn)
                group["TagList"] = tags_response.get("TagList", [])
            return ResourceDetails(
                title=f"RDS DB Cluster Parameter Group: {group['DBClusterParameterGroupName']}",
                subtitle=arn,
                summary={
                    "Name": group.get("DBClusterParameterGroupName", ""),
                    "Family": group.get("DBParameterGroupFamily", ""),
                    "Description": group.get("Description", ""),
                },
                raw=group,
            )

        if node.node_type == "db_snapshot":
            response = client.describe_db_snapshots(
                DBSnapshotIdentifier=node.metadata["db_snapshot_id"]
            )
            snapshot = response["DBSnapshots"][0]
            arn = snapshot.get("DBSnapshotArn", "")
            if arn:
                tags_response = client.list_tags_for_resource(ResourceName=arn)
                snapshot["TagList"] = tags_response.get("TagList", [])
            return ResourceDetails(
                title=f"RDS DB Snapshot: {snapshot['DBSnapshotIdentifier']}",
                subtitle=arn,
                summary={
                    "Identifier": snapshot.get("DBSnapshotIdentifier", ""),
                    "DB Instance": snapshot.get("DBInstanceIdentifier", ""),
                    "Type": snapshot.get("SnapshotType", ""),
                    "Status": snapshot.get("Status", ""),
                    "Engine": snapshot.get("Engine", ""),
                    "Engine Version": snapshot.get("EngineVersion", ""),
                    "Storage (GB)": str(snapshot.get("AllocatedStorage", "")),
                    "Created": str(snapshot.get("SnapshotCreateTime", "")),
                    "Encrypted": str(snapshot.get("Encrypted", "")),
                },
                raw=snapshot,
            )

        if node.node_type == "db_cluster_snapshot":
            response = client.describe_db_cluster_snapshots(
                DBClusterSnapshotIdentifier=node.metadata["db_cluster_snapshot_id"]
            )
            snapshot = response["DBClusterSnapshots"][0]
            arn = snapshot.get("DBClusterSnapshotArn", "")
            if arn:
                tags_response = client.list_tags_for_resource(ResourceName=arn)
                snapshot["TagList"] = tags_response.get("TagList", [])
            return ResourceDetails(
                title=f"RDS DB Cluster Snapshot: {snapshot['DBClusterSnapshotIdentifier']}",
                subtitle=arn,
                summary={
                    "Identifier": snapshot.get("DBClusterSnapshotIdentifier", ""),
                    "DB Cluster": snapshot.get("DBClusterIdentifier", ""),
                    "Type": snapshot.get("SnapshotType", ""),
                    "Status": snapshot.get("Status", ""),
                    "Engine": snapshot.get("Engine", ""),
                    "Engine Version": snapshot.get("EngineVersion", ""),
                    "Storage (GB)": str(snapshot.get("AllocatedStorage", "")),
                    "Created": str(snapshot.get("SnapshotCreateTime", "")),
                    "Encrypted": str(snapshot.get("StorageEncrypted", "")),
                },
                raw=snapshot,
            )

        if node.node_type == "option_group":
            response = client.describe_option_groups(
                OptionGroupName=node.metadata["option_group_name"]
            )
            group = response["OptionGroupsList"][0]
            arn = group.get("OptionGroupArn", "")
            if arn:
                tags_response = client.list_tags_for_resource(ResourceName=arn)
                group["TagList"] = tags_response.get("TagList", [])
            return ResourceDetails(
                title=f"RDS Option Group: {group['OptionGroupName']}",
                subtitle=arn,
                summary={
                    "Name": group.get("OptionGroupName", ""),
                    "Engine": group.get("EngineName", ""),
                    "Major Engine Version": group.get("MajorEngineVersion", ""),
                    "Description": group.get("OptionGroupDescription", ""),
                    "Options": str(len(group.get("Options", []))),
                },
                raw=group,
            )

        if node.node_type == "category":
            return ResourceDetails(
                title=node.label, subtitle="Expand to see resources", summary={}, raw={}
            )

        return ResourceDetails(title=node.label, subtitle="", summary={}, raw={})


plugin = RDSPlugin()
