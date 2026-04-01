from __future__ import annotations

import boto3

from awstui.models import ResourceDetails, TreeNode
from awstui.plugin import AWSServicePlugin


class S3Plugin(AWSServicePlugin):
    @property
    def name(self) -> str:
        return "S3"

    @property
    def service_name(self) -> str:
        return "s3"

    def get_root_nodes(self, session: boto3.Session) -> list[TreeNode]:
        client = session.client("s3")
        response = client.list_buckets()
        return [
            TreeNode(
                id=f"s3:bucket:{b['Name']}",
                label=b["Name"],
                node_type="bucket",
                service="s3",
                expandable=True,
                metadata={"bucket_name": b["Name"]},
            )
            for b in response.get("Buckets", [])
        ]

    def get_children(self, session: boto3.Session, node: TreeNode) -> list[TreeNode]:
        if node.node_type not in ("bucket", "prefix"):
            return []

        client = session.client("s3")
        bucket = node.metadata["bucket_name"]
        prefix = node.metadata.get("prefix", "")

        response = client.list_objects_v2(
            Bucket=bucket, Prefix=prefix, Delimiter="/"
        )

        children: list[TreeNode] = []

        for cp in response.get("CommonPrefixes", []):
            p = cp["Prefix"]
            display = p[len(prefix) :]
            children.append(
                TreeNode(
                    id=f"s3:prefix:{bucket}:{p}",
                    label=display,
                    node_type="prefix",
                    service="s3",
                    expandable=True,
                    metadata={"bucket_name": bucket, "prefix": p},
                )
            )

        for obj in response.get("Contents", []):
            key = obj["Key"]
            if key == prefix:
                continue
            display = key[len(prefix) :]
            children.append(
                TreeNode(
                    id=f"s3:object:{bucket}:{key}",
                    label=display,
                    node_type="object",
                    service="s3",
                    expandable=False,
                    metadata={"bucket_name": bucket, "key": key},
                )
            )

        return children

    def get_details(self, session: boto3.Session, node: TreeNode) -> ResourceDetails:
        client = session.client("s3")

        if node.node_type == "bucket":
            bucket = node.metadata["bucket_name"]
            location = client.get_bucket_location(Bucket=bucket)
            region = location.get("LocationConstraint") or "us-east-1"
            return ResourceDetails(
                title=f"S3 Bucket: {bucket}",
                subtitle=f"arn:aws:s3:::{bucket}",
                summary={
                    "Name": bucket,
                    "Location": region,
                },
                raw=location,
            )

        if node.node_type == "object":
            bucket = node.metadata["bucket_name"]
            key = node.metadata["key"]
            head = client.head_object(Bucket=bucket, Key=key)
            return ResourceDetails(
                title=f"S3 Object: {node.label}",
                subtitle=f"s3://{bucket}/{key}",
                summary={
                    "Key": key,
                    "Size": str(head.get("ContentLength", "")),
                    "Content Type": head.get("ContentType", ""),
                    "Last Modified": str(head.get("LastModified", "")),
                    "ETag": head.get("ETag", ""),
                    "Storage Class": head.get("StorageClass", "STANDARD"),
                },
                raw=head,
            )

        if node.node_type == "prefix":
            bucket = node.metadata["bucket_name"]
            prefix = node.metadata["prefix"]
            return ResourceDetails(
                title=f"S3 Prefix: {prefix}",
                subtitle=f"s3://{bucket}/{prefix}",
                summary={"Bucket": bucket, "Prefix": prefix},
                raw={"Bucket": bucket, "Prefix": prefix},
            )

        return ResourceDetails(
            title=node.label, subtitle="", summary={}, raw={}
        )


plugin = S3Plugin()
