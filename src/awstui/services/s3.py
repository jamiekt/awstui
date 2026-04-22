from __future__ import annotations

import boto3
from botocore.exceptions import ClientError

from awstui.models import ResourceDetails, TreeNode
from awstui.plugin import AWSServicePlugin


class S3Plugin(AWSServicePlugin):
    @property
    def name(self) -> str:
        return "S3"

    @property
    def service_name(self) -> str:
        return "s3"

    @property
    def has_flat_root(self) -> bool:
        return False

    def get_root_nodes(self, session: boto3.Session) -> list[TreeNode]:
        return [
            TreeNode(
                id="s3:category:general_purpose_buckets",
                label="General purpose buckets",
                node_type="category",
                service="s3",
                expandable=True,
                metadata={"category": "general_purpose_buckets"},
            ),
            TreeNode(
                id="s3:category:directory_buckets",
                label="Directory buckets",
                node_type="category",
                service="s3",
                expandable=True,
                metadata={"category": "directory_buckets"},
            ),
            TreeNode(
                id="s3:category:table_buckets",
                label="Table buckets",
                node_type="category",
                service="s3",
                expandable=True,
                metadata={"category": "table_buckets"},
            ),
            TreeNode(
                id="s3:category:vector_buckets",
                label="Vector buckets",
                node_type="category",
                service="s3",
                expandable=True,
                metadata={"category": "vector_buckets"},
            ),
            TreeNode(
                id="s3:category:access_points",
                label="Access points",
                node_type="category",
                service="s3",
                expandable=True,
                metadata={"category": "access_points"},
            ),
        ]

    def get_children(self, session: boto3.Session, node: TreeNode) -> list[TreeNode]:
        if node.metadata.get("category") == "general_purpose_buckets":
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

        if node.metadata.get("category") == "directory_buckets":
            client = session.client("s3")
            response = client.list_directory_buckets()
            return [
                TreeNode(
                    id=f"s3:directory_bucket:{b['Name']}",
                    label=b["Name"],
                    node_type="directory_bucket",
                    service="s3",
                    expandable=False,
                    metadata={"bucket_name": b["Name"]},
                )
                for b in response.get("Buckets", [])
            ]

        if node.metadata.get("category") == "table_buckets":
            client = session.client("s3tables")
            response = client.list_table_buckets()
            return [
                TreeNode(
                    id=f"s3:table_bucket:{b['arn']}",
                    label=b["name"],
                    node_type="table_bucket",
                    service="s3",
                    expandable=False,
                    metadata={
                        "table_bucket_arn": b["arn"],
                        "table_bucket_name": b["name"],
                    },
                )
                for b in response.get("tableBuckets", [])
            ]

        if node.metadata.get("category") == "vector_buckets":
            client = session.client("s3vectors")
            response = client.list_vector_buckets()
            return [
                TreeNode(
                    id=f"s3:vector_bucket:{b['vectorBucketArn']}",
                    label=b["vectorBucketName"],
                    node_type="vector_bucket",
                    service="s3",
                    expandable=False,
                    metadata={
                        "vector_bucket_name": b["vectorBucketName"],
                        "vector_bucket_arn": b["vectorBucketArn"],
                    },
                )
                for b in response.get("vectorBuckets", [])
            ]

        if node.metadata.get("category") == "access_points":
            sts = session.client("sts")
            account_id = sts.get_caller_identity()["Account"]
            client = session.client("s3control")
            response = client.list_access_points(AccountId=account_id)
            return [
                TreeNode(
                    id=f"s3:access_point:{ap['AccessPointArn']}",
                    label=ap["Name"],
                    node_type="access_point",
                    service="s3",
                    expandable=False,
                    metadata={
                        "access_point_name": ap["Name"],
                        "access_point_arn": ap["AccessPointArn"],
                        "account_id": account_id,
                    },
                )
                for ap in response.get("AccessPointList", [])
            ]

        if node.node_type not in ("bucket", "prefix"):
            return []

        client = session.client("s3")
        bucket = node.metadata["bucket_name"]
        prefix = node.metadata.get("prefix", "")

        response = client.list_objects_v2(Bucket=bucket, Prefix=prefix, Delimiter="/")

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
            try:
                tagging = client.get_bucket_tagging(Bucket=bucket)
                tag_set = tagging.get("TagSet", [])
            except ClientError as e:
                # NoSuchTagSet is returned when the bucket has no tags.
                if e.response["Error"].get("Code") == "NoSuchTagSet":
                    tag_set = []
                else:
                    raise
            raw = {**location, "TagSet": tag_set}
            return ResourceDetails(
                title=f"S3 Bucket: {bucket}",
                subtitle=f"arn:aws:s3:::{bucket}",
                summary={
                    "Name": bucket,
                    "Location": region,
                },
                raw=raw,
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

        if node.node_type == "directory_bucket":
            bucket = node.metadata["bucket_name"]
            return ResourceDetails(
                title=f"S3 Directory Bucket: {bucket}",
                subtitle=f"arn:aws:s3express:::{bucket}",
                summary={"Name": bucket},
                raw={"Name": bucket},
            )

        if node.node_type == "vector_bucket":
            vclient = session.client("s3vectors")
            arn = node.metadata["vector_bucket_arn"]
            name = node.metadata["vector_bucket_name"]
            response = vclient.get_vector_bucket(vectorBucketName=name)
            bucket = response.get("vectorBucket", {})
            try:
                tags_response = vclient.list_tags_for_resource(resourceArn=arn)
                bucket["TagList"] = tags_response.get("tags", [])
            except ClientError:
                bucket["TagList"] = []
            return ResourceDetails(
                title=f"S3 Vector Bucket: {bucket.get('vectorBucketName', name)}",
                subtitle=arn,
                summary={
                    "Name": bucket.get("vectorBucketName", ""),
                    "Created": str(bucket.get("creationTime", "")),
                },
                raw=bucket,
            )

        if node.node_type == "access_point":
            control = session.client("s3control")
            name = node.metadata["access_point_name"]
            account_id = node.metadata["account_id"]
            arn = node.metadata["access_point_arn"]
            ap = control.get_access_point(AccountId=account_id, Name=name)
            ap.pop("ResponseMetadata", None)
            return ResourceDetails(
                title=f"S3 Access Point: {ap.get('Name', name)}",
                subtitle=arn,
                summary={
                    "Name": ap.get("Name", ""),
                    "Bucket": ap.get("Bucket", ""),
                    "Network Origin": ap.get("NetworkOrigin", ""),
                    "Alias": ap.get("Alias", ""),
                    "Created": str(ap.get("CreationDate", "")),
                },
                raw=ap,
            )

        if node.node_type == "table_bucket":
            tables_client = session.client("s3tables")
            arn = node.metadata["table_bucket_arn"]
            bucket = tables_client.get_table_bucket(tableBucketARN=arn)
            try:
                tags_response = tables_client.list_tags_for_resource(resourceArn=arn)
                bucket["TagList"] = tags_response.get("tags", [])
            except ClientError:
                bucket["TagList"] = []
            return ResourceDetails(
                title=f"S3 Table Bucket: {bucket.get('name', '')}",
                subtitle=arn,
                summary={
                    "Name": bucket.get("name", ""),
                    "Type": bucket.get("type", ""),
                    "Owner Account": bucket.get("ownerAccountId", ""),
                    "Created": str(bucket.get("createdAt", "")),
                },
                raw=bucket,
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

        if node.node_type == "category":
            return ResourceDetails(
                title=node.label, subtitle="Expand to see resources", summary={}, raw={}
            )

        return ResourceDetails(title=node.label, subtitle="", summary={}, raw={})


plugin = S3Plugin()
