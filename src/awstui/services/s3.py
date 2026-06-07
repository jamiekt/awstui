from __future__ import annotations

from collections.abc import Iterator

import boto3
from botocore.exceptions import ClientError

from awstui.models import ContentPreview, ResourceDetails, TreeNode
from awstui.plugin import AWSServicePlugin
from awstui.util import human_bytes

# Maximum number of bytes of object content to fetch for preview.
_CONTENT_PREVIEW_MAX_BYTES = 1_000_000

# Content-types we treat as "generic" — extension sniffing takes over.
_GENERIC_CONTENT_TYPES = {
    "",
    "application/octet-stream",
    "binary/octet-stream",
}

# Content-types (prefix match) we consider textual and safe to render.
_TEXTUAL_PREFIXES = ("text/",)
_TEXTUAL_EXACT = {
    "application/json",
    "application/xml",
    "application/x-yaml",
    "application/yaml",
    "application/javascript",
    "application/x-javascript",
    "application/typescript",
    "application/x-www-form-urlencoded",
    "application/x-sh",
}

# File extensions we treat as text when content-type is missing or generic.
_TEXTUAL_EXTENSIONS = {
    ".txt",
    ".log",
    ".md",
    ".csv",
    ".tsv",
    ".json",
    ".yaml",
    ".yml",
    ".xml",
    ".html",
    ".htm",
    ".css",
    ".js",
    ".ts",
    ".py",
    ".rb",
    ".go",
    ".rs",
    ".sh",
    ".bash",
    ".zsh",
    ".ini",
    ".cfg",
    ".toml",
    ".conf",
    ".sql",
    ".tf",
}

# Object extensions for which the SQL tab is offered.
_SQL_EXTENSIONS = {".parquet", ".csv", ".tsv"}


# Map content-type / extension to a Rich syntax lexer name.
_LANGUAGE_MAP = {
    "application/json": "json",
    "application/xml": "xml",
    "application/x-yaml": "yaml",
    "application/yaml": "yaml",
    "application/javascript": "javascript",
    "application/x-javascript": "javascript",
    "application/typescript": "typescript",
    "application/x-sh": "bash",
    "text/html": "html",
    "text/css": "css",
    "text/xml": "xml",
    "text/csv": "csv",
    "text/tab-separated-values": "csv",
    "text/markdown": "markdown",
}
_EXTENSION_LANGUAGE_MAP = {
    ".csv": "csv",
    ".tsv": "csv",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".xml": "xml",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".js": "javascript",
    ".ts": "typescript",
    ".py": "python",
    ".rb": "ruby",
    ".go": "go",
    ".rs": "rust",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "bash",
    ".md": "markdown",
    ".toml": "toml",
    ".ini": "ini",
    ".sql": "sql",
    ".tf": "hcl",
}


def _is_textual(content_type: str, key: str) -> bool:
    ct = (content_type or "").split(";", 1)[0].strip().lower()
    if any(ct.startswith(p) for p in _TEXTUAL_PREFIXES):
        return True
    if ct in _TEXTUAL_EXACT:
        return True
    # Fall back to extension sniffing for objects with no or generic type.
    ext = _extension(key)
    if ct in _GENERIC_CONTENT_TYPES and ext in _TEXTUAL_EXTENSIONS:
        return True
    return False


def _language_for(content_type: str, key: str) -> str | None:
    ct = (content_type or "").split(";", 1)[0].strip().lower()
    if ct in _LANGUAGE_MAP:
        return _LANGUAGE_MAP[ct]
    ext = _extension(key)
    return _EXTENSION_LANGUAGE_MAP.get(ext)


def _extension(key: str) -> str:
    dot = key.rfind(".")
    slash = key.rfind("/")
    if dot == -1 or dot < slash:
        return ""
    return key[dot:].lower()


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

        if node.node_type == "object":
            return _build_version_children(session, node)

        if node.node_type not in ("bucket", "prefix"):
            return []

        client = session.client("s3")
        bucket = node.metadata["bucket_name"]
        prefix = node.metadata.get("prefix", "")

        # One versioning check per bucket walk — cached on each object /
        # prefix child so they don't re-query. `None` means "unknown" and
        # causes the object to stay non-expandable (safe default).
        versioning_enabled = node.metadata.get("versioning_enabled")
        if versioning_enabled is None:
            versioning_enabled = _bucket_versioning_enabled(client, bucket)

        paginator = client.get_paginator("list_objects_v2")
        children: list[TreeNode] = []

        for page in paginator.paginate(Bucket=bucket, Prefix=prefix, Delimiter="/"):
            for cp in page.get("CommonPrefixes", []):
                p = cp["Prefix"]
                display = p[len(prefix) :]
                children.append(
                    TreeNode(
                        id=f"s3:prefix:{bucket}:{p}",
                        label=display,
                        node_type="prefix",
                        service="s3",
                        expandable=True,
                        metadata={
                            "bucket_name": bucket,
                            "prefix": p,
                            "versioning_enabled": versioning_enabled,
                        },
                    )
                )

            for obj in page.get("Contents", []):
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
                        expandable=bool(versioning_enabled),
                        metadata={
                            "bucket_name": bucket,
                            "key": key,
                            "size": obj.get("Size"),
                            "versioning_enabled": versioning_enabled,
                        },
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
            summary_groups: list[tuple[str, dict[str, str]]] = []
            versions = _list_object_versions(client, bucket, key)
            if versions:
                summary_groups.append(("Versions", versions))
            return ResourceDetails(
                title=f"S3 Object: {node.label}",
                subtitle=f"arn:aws:s3:::{bucket}/{key}",
                summary={
                    "Key": key,
                    "URI": f"s3://{bucket}/{key}",
                    "Size": str(head.get("ContentLength", "")),
                    "Content Type": head.get("ContentType", ""),
                    "Last Modified": str(head.get("LastModified", "")),
                    "ETag": head.get("ETag", ""),
                    "Storage Class": head.get("StorageClass", "STANDARD"),
                },
                raw=head,
                summary_groups=summary_groups,
            )

        if node.node_type == "object_version":
            bucket = node.metadata["bucket_name"]
            key = node.metadata["key"]
            version_id = node.metadata["version_id"]
            tags: list[str] = []
            if node.metadata.get("is_latest"):
                tags.append("latest")
            if node.metadata.get("is_delete_marker"):
                tags.append("delete marker")
            summary = {
                "Key": key,
                "Version ID": version_id,
                "Last Modified": str(node.metadata.get("last_modified", "")),
                "URI": f"s3://{bucket}/{key}?versionId={version_id}",
            }
            if node.metadata.get("size") is not None:
                summary["Size"] = str(node.metadata["size"])
            if tags:
                summary["Status"] = ", ".join(tags)
            return ResourceDetails(
                title=f"S3 Object Version: {key}",
                subtitle=f"arn:aws:s3:::{bucket}/{key}",
                summary=summary,
                raw={
                    "Bucket": bucket,
                    "Key": key,
                    "VersionId": version_id,
                    "IsLatest": node.metadata.get("is_latest", False),
                    "IsDeleteMarker": node.metadata.get("is_delete_marker", False),
                    "Size": node.metadata.get("size"),
                    "LastModified": node.metadata.get("last_modified", ""),
                },
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

    def supports_size(self, node: TreeNode) -> bool:
        return node.node_type in ("bucket", "prefix", "object")

    def iter_size(
        self, session: boto3.Session, node: TreeNode
    ) -> Iterator[tuple[int, int, dict[str, tuple[int, int]]]]:
        if node.node_type == "object":
            yield int(node.metadata.get("size") or 0), 1, {}
            return
        # bucket / prefix recursive walk
        client = session.client("s3")
        bucket = node.metadata["bucket_name"]
        prefix = node.metadata.get("prefix", "")
        paginator = client.get_paginator("list_objects_v2")
        total = 0
        count = 0
        descendants: dict[str, tuple[int, int]] = {}
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                size = obj.get("Size", 0)
                total += size
                count += 1
                for p in _descendant_prefixes(prefix, obj["Key"]):
                    node_id = f"s3:prefix:{bucket}:{p}"
                    b, c = descendants.get(node_id, (0, 0))
                    descendants[node_id] = (b + size, c + 1)
            yield total, count, dict(descendants)

    def has_content(self, node: TreeNode) -> bool:
        if node.node_type == "object":
            return True
        if node.node_type == "object_version":
            # Delete markers have no body to preview.
            return not node.metadata.get("is_delete_marker", False)
        return False

    def get_content(
        self, session: boto3.Session, node: TreeNode
    ) -> ContentPreview | None:
        if node.node_type == "object":
            return _preview_s3_object(session, node, version_id=None)
        if node.node_type == "object_version":
            if node.metadata.get("is_delete_marker"):
                return ContentPreview(
                    kind="message",
                    body="Delete marker — no content",
                )
            return _preview_s3_object(
                session, node, version_id=node.metadata["version_id"]
            )
        return None

    def has_sql(self, node: TreeNode) -> bool:
        if node.node_type not in ("object", "object_version"):
            return False
        if node.node_type == "object_version" and node.metadata.get("is_delete_marker"):
            return False
        return _extension(node.metadata.get("key", "")) in _SQL_EXTENSIONS

    def default_sql(self, node: TreeNode) -> str | None:
        if not self.has_sql(node):
            return None
        bucket = node.metadata["bucket_name"]
        key = node.metadata["key"]
        ext = _extension(key)
        path = f"s3://{bucket}/{key}"
        if ext == ".parquet":
            return f"SELECT *\nFROM read_parquet('{path}')"
        # .csv / .tsv — DuckDB's read_csv_auto handles both delimiters.
        return f"SELECT *\nFROM read_csv_auto('{path}')"


_MAX_VERSIONS_SHOWN = 100


def _preview_s3_object(
    session: boto3.Session, node: TreeNode, version_id: str | None
) -> ContentPreview | None:
    """Build a ContentPreview for an S3 object, optionally a specific version.

    Mirrors the original in-line object preview code but parameterised so
    object_version nodes can call it with a VersionId.
    """
    client = session.client("s3")
    bucket = node.metadata["bucket_name"]
    key = node.metadata["key"]

    head_kwargs: dict = {"Bucket": bucket, "Key": key}
    if version_id:
        head_kwargs["VersionId"] = version_id
    head = client.head_object(**head_kwargs)
    size = int(head.get("ContentLength", 0))
    content_type = head.get("ContentType", "") or ""

    if not _is_textual(content_type, key):
        return ContentPreview(
            kind="binary",
            body=(
                f"Binary content · {human_bytes(size)} · "
                f"{content_type or 'unknown content-type'}"
            ),
            size=size,
        )

    truncated = size > _CONTENT_PREVIEW_MAX_BYTES
    get_kwargs: dict = {"Bucket": bucket, "Key": key}
    if version_id:
        get_kwargs["VersionId"] = version_id
    if truncated:
        get_kwargs["Range"] = f"bytes=0-{_CONTENT_PREVIEW_MAX_BYTES - 1}"

    response = client.get_object(**get_kwargs)
    raw_bytes = response["Body"].read()
    try:
        body = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        body = raw_bytes.decode("utf-8", errors="replace")

    return ContentPreview(
        kind="text",
        body=body,
        language=_language_for(content_type, key),
        size=size,
        truncated=truncated,
    )


def _descendant_prefixes(root_prefix: str, key: str) -> Iterator[str]:
    """Yield each intermediate directory prefix of `key` below `root_prefix`.

    e.g. root_prefix="logs/", key="logs/2026/01/a" yields
    "logs/2026/", "logs/2026/01/". A key with no "/" below the root yields
    nothing. Each yielded value matches the prefix string `get_children`
    uses to build a prefix node's id.
    """
    if not key.startswith(root_prefix):
        return
    remainder = key[len(root_prefix) :]
    idx = remainder.find("/")
    while idx != -1:
        yield root_prefix + remainder[: idx + 1]
        idx = remainder.find("/", idx + 1)


def _bucket_versioning_enabled(client, bucket: str) -> bool:
    """Return True if the bucket has versioning enabled, False otherwise
    (including if the call fails — we just treat it as 'no'.)"""
    try:
        return client.get_bucket_versioning(Bucket=bucket).get("Status") == "Enabled"
    except ClientError:
        return False


def _build_version_children(session: boto3.Session, node: TreeNode) -> list[TreeNode]:
    """Build the version TreeNodes that appear under an S3 object."""
    client = session.client("s3")
    bucket = node.metadata["bucket_name"]
    key = node.metadata["key"]
    records = _fetch_object_versions(client, bucket, key)
    children: list[TreeNode] = []
    for record in records[:_MAX_VERSIONS_SHOWN]:
        version_id = record["version_id"]
        children.append(
            TreeNode(
                id=f"s3:object_version:{bucket}:{key}:{version_id}",
                label=_version_node_label(record),
                node_type="object_version",
                service="s3",
                expandable=False,
                metadata={
                    "bucket_name": bucket,
                    "key": key,
                    "version_id": version_id,
                    "is_latest": record["is_latest"],
                    "is_delete_marker": record["is_delete_marker"],
                    "size": record["size"],
                    "last_modified": record["last_modified"],
                },
            )
        )
    return children


def _fetch_object_versions(client, bucket: str, key: str) -> list[dict]:
    """Return the raw version + delete-marker records for a single S3 object.

    Returns an empty list when the bucket doesn't have versioning enabled.
    Stops fetching once `_MAX_VERSIONS_SHOWN + 1` entries have been
    collected — callers use the "+1" to detect truncation.
    """
    try:
        status = client.get_bucket_versioning(Bucket=bucket).get("Status")
    except ClientError:
        return []
    if status != "Enabled":
        return []

    paginator = client.get_paginator("list_object_versions")
    records: list[dict] = []
    limit = _MAX_VERSIONS_SHOWN + 1
    for page in paginator.paginate(Bucket=bucket, Prefix=key):
        for v in page.get("Versions", []):
            if v.get("Key") != key:
                continue
            records.append(
                {
                    "version_id": v.get("VersionId", ""),
                    "last_modified": str(v.get("LastModified", "")),
                    "is_latest": bool(v.get("IsLatest", False)),
                    "size": v.get("Size"),
                    "is_delete_marker": False,
                }
            )
        for dm in page.get("DeleteMarkers", []):
            if dm.get("Key") != key:
                continue
            records.append(
                {
                    "version_id": dm.get("VersionId", ""),
                    "last_modified": str(dm.get("LastModified", "")),
                    "is_latest": bool(dm.get("IsLatest", False)),
                    "size": None,
                    "is_delete_marker": True,
                }
            )
        if len(records) >= limit:
            break
    return records


def _format_version_records(records: list[dict]) -> dict[str, str]:
    """Turn fetched version records into a {version_id -> description} dict
    for the Summary tab. Capped at _MAX_VERSIONS_SHOWN; a synthetic "..."
    row is appended when truncated.
    """
    result: dict[str, str] = {}
    for record in records[:_MAX_VERSIONS_SHOWN]:
        parts: list[str] = [record["last_modified"]]
        size = record["size"]
        if size is not None:
            parts.append(human_bytes(int(size)))
        tags: list[str] = []
        if record["is_latest"]:
            tags.append("latest")
        if record["is_delete_marker"]:
            tags.append("delete marker")
        if tags:
            parts.append(", ".join(tags))
        result[record["version_id"]] = " · ".join(parts)

    if len(records) > _MAX_VERSIONS_SHOWN:
        omitted = len(records) - _MAX_VERSIONS_SHOWN
        result["..."] = f"{omitted} more version(s) omitted"
    return result


def _list_object_versions(client, bucket: str, key: str) -> dict[str, str]:
    """Legacy wrapper used by the summary path: fetch + format in one call."""
    return _format_version_records(_fetch_object_versions(client, bucket, key))


def _version_node_label(record: dict) -> str:
    """Short label for a version node in the nav tree."""
    parts = [record["last_modified"].replace("T", " ").rstrip("Z")]
    tags: list[str] = []
    if record["is_latest"]:
        tags.append("latest")
    if record["is_delete_marker"]:
        tags.append("delete marker")
    if tags:
        parts.append(", ".join(tags))
    return " · ".join(parts)


plugin = S3Plugin()
