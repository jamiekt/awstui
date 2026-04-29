from unittest.mock import MagicMock

from awstui.services.s3 import S3Plugin


def make_session():
    return MagicMock()


def test_s3_plugin_properties():
    plugin = S3Plugin()
    assert plugin.name == "S3"
    assert plugin.service_name == "s3"


def test_get_root_nodes_returns_categories():
    session = make_session()

    plugin = S3Plugin()
    nodes = plugin.get_root_nodes(session)

    assert len(nodes) == 5
    labels = [n.label for n in nodes]
    assert "General purpose buckets" in labels
    assert "Directory buckets" in labels
    assert "Table buckets" in labels
    assert "Access points" in labels
    assert "Vector buckets" in labels
    assert all(n.node_type == "category" for n in nodes)
    assert all(n.expandable for n in nodes)


def test_get_children_of_general_purpose_buckets_category():
    session = make_session()
    client = session.client.return_value
    client.list_buckets.return_value = {
        "Buckets": [
            {"Name": "bucket-a", "CreationDate": "2026-01-01T00:00:00Z"},
            {"Name": "bucket-b", "CreationDate": "2026-01-02T00:00:00Z"},
        ]
    }

    from awstui.models import TreeNode

    category_node = TreeNode(
        id="s3:category:general_purpose_buckets",
        label="General purpose buckets",
        node_type="category",
        service="s3",
        expandable=True,
        metadata={"category": "general_purpose_buckets"},
    )

    plugin = S3Plugin()
    children = plugin.get_children(session, category_node)

    assert len(children) == 2
    assert children[0].label == "bucket-a"
    assert children[0].node_type == "bucket"
    assert children[0].expandable is True
    assert children[0].metadata["bucket_name"] == "bucket-a"


def test_get_children_of_bucket_lists_prefixes_and_objects():
    session = make_session()
    client = session.client.return_value
    client.get_paginator.return_value.paginate.return_value = [
        {
            "CommonPrefixes": [{"Prefix": "logs/"}],
            "Contents": [{"Key": "readme.txt", "Size": 1024}],
        }
    ]

    from awstui.models import TreeNode

    bucket_node = TreeNode(
        id="s3:bucket:my-bucket",
        label="my-bucket",
        node_type="bucket",
        service="s3",
        expandable=True,
        metadata={"bucket_name": "my-bucket"},
    )

    plugin = S3Plugin()
    children = plugin.get_children(session, bucket_node)

    assert len(children) == 2
    prefixes = [c for c in children if c.node_type == "prefix"]
    objects = [c for c in children if c.node_type == "object"]
    assert len(prefixes) == 1
    assert prefixes[0].label == "logs/"
    assert prefixes[0].expandable is True
    assert len(objects) == 1
    assert objects[0].label == "readme.txt"
    assert objects[0].expandable is False


def test_get_children_of_prefix():
    session = make_session()
    client = session.client.return_value
    client.get_paginator.return_value.paginate.return_value = [
        {
            "CommonPrefixes": [],
            "Contents": [{"Key": "logs/app.log", "Size": 2048}],
        }
    ]

    from awstui.models import TreeNode

    prefix_node = TreeNode(
        id="s3:prefix:my-bucket:logs/",
        label="logs/",
        node_type="prefix",
        service="s3",
        expandable=True,
        metadata={"bucket_name": "my-bucket", "prefix": "logs/"},
    )

    plugin = S3Plugin()
    children = plugin.get_children(session, prefix_node)

    assert len(children) == 1
    assert children[0].label == "app.log"
    assert children[0].node_type == "object"


def test_get_children_of_prefix_pagination():
    """Children from multiple pages should all be returned."""
    session = make_session()
    client = session.client.return_value
    client.get_paginator.return_value.paginate.return_value = [
        {
            "CommonPrefixes": [],
            "Contents": [{"Key": f"logs/file-{i:04d}.log"} for i in range(1000)],
        },
        {
            "CommonPrefixes": [],
            "Contents": [{"Key": f"logs/file-{i:04d}.log"} for i in range(1000, 1500)],
        },
    ]

    from awstui.models import TreeNode

    prefix_node = TreeNode(
        id="s3:prefix:my-bucket:logs/",
        label="logs/",
        node_type="prefix",
        service="s3",
        expandable=True,
        metadata={"bucket_name": "my-bucket", "prefix": "logs/"},
    )

    plugin = S3Plugin()
    children = plugin.get_children(session, prefix_node)

    assert len(children) == 1500


def test_get_details_for_bucket():
    session = make_session()
    client = session.client.return_value
    client.get_bucket_location.return_value = {"LocationConstraint": "us-west-2"}

    from awstui.models import TreeNode

    bucket_node = TreeNode(
        id="s3:bucket:my-bucket",
        label="my-bucket",
        node_type="bucket",
        service="s3",
        expandable=True,
        metadata={"bucket_name": "my-bucket"},
    )

    plugin = S3Plugin()
    details = plugin.get_details(session, bucket_node)

    assert details.title == "S3 Bucket: my-bucket"
    assert "Name" in details.summary
    assert "Location" in details.summary


def test_get_details_for_object():
    session = make_session()
    client = session.client.return_value
    client.head_object.return_value = {
        "ContentLength": 1024,
        "ContentType": "text/plain",
        "LastModified": "2026-03-28T14:32:01Z",
        "ETag": '"abc123"',
        "StorageClass": "STANDARD",
    }

    from awstui.models import TreeNode

    obj_node = TreeNode(
        id="s3:object:my-bucket:readme.txt",
        label="readme.txt",
        node_type="object",
        service="s3",
        expandable=False,
        metadata={"bucket_name": "my-bucket", "key": "readme.txt"},
    )

    plugin = S3Plugin()
    details = plugin.get_details(session, obj_node)

    assert details.title == "S3 Object: readme.txt"
    assert "Size" in details.summary
    assert "Content Type" in details.summary
    # Versioning not enabled on this mock bucket, so no Versions group.
    assert details.summary_groups == []


def test_get_details_for_object_includes_versions_when_enabled():
    session = make_session()
    client = session.client.return_value
    client.head_object.return_value = {
        "ContentLength": 1024,
        "ContentType": "text/plain",
        "LastModified": "2026-03-28T14:32:01Z",
    }
    client.get_bucket_versioning.return_value = {"Status": "Enabled"}
    # The paginator returns two pages, each mixing other-key entries to
    # prove we filter by exact key match.
    client.get_paginator.return_value.paginate.return_value = [
        {
            "Versions": [
                {
                    "Key": "readme.txt",
                    "VersionId": "v3",
                    "LastModified": "2026-03-28T14:32:01Z",
                    "IsLatest": True,
                    "Size": 1024,
                },
                {
                    "Key": "other.txt",
                    "VersionId": "vOther",
                    "LastModified": "2026-03-28T14:32:01Z",
                    "IsLatest": True,
                    "Size": 1,
                },
            ],
            "DeleteMarkers": [],
        },
        {
            "Versions": [
                {
                    "Key": "readme.txt",
                    "VersionId": "v1",
                    "LastModified": "2026-02-01T00:00:00Z",
                    "IsLatest": False,
                    "Size": 256,
                },
            ],
            "DeleteMarkers": [
                {
                    "Key": "readme.txt",
                    "VersionId": "v2-dm",
                    "LastModified": "2026-03-01T00:00:00Z",
                    "IsLatest": False,
                },
            ],
        },
    ]

    from awstui.models import TreeNode

    obj_node = TreeNode(
        id="s3:object:my-bucket:readme.txt",
        label="readme.txt",
        node_type="object",
        service="s3",
        expandable=False,
        metadata={"bucket_name": "my-bucket", "key": "readme.txt"},
    )

    plugin = S3Plugin()
    details = plugin.get_details(session, obj_node)

    groups = dict(details.summary_groups)
    assert "Versions" in groups
    versions = groups["Versions"]
    # Filtered out the "other.txt" version; kept the three for readme.txt.
    assert set(versions.keys()) == {"v3", "v2-dm", "v1"}
    assert "latest" in versions["v3"]
    assert "delete marker" in versions["v2-dm"]
    # Non-latest, non-dm versions should not carry a tag.
    assert "latest" not in versions["v1"]
    assert "delete marker" not in versions["v1"]


def test_get_details_for_object_no_versions_group_when_versioning_off():
    session = make_session()
    client = session.client.return_value
    client.head_object.return_value = {"ContentLength": 0, "ContentType": "text/plain"}
    client.get_bucket_versioning.return_value = {"Status": "Suspended"}

    from awstui.models import TreeNode

    obj_node = TreeNode(
        id="s3:object:my-bucket:readme.txt",
        label="readme.txt",
        node_type="object",
        service="s3",
        expandable=False,
        metadata={"bucket_name": "my-bucket", "key": "readme.txt"},
    )

    plugin = S3Plugin()
    details = plugin.get_details(session, obj_node)
    assert details.summary_groups == []
    # list_object_versions should never have been called.
    client.get_paginator.assert_not_called()


def test_get_details_for_object_truncates_many_versions():
    session = make_session()
    client = session.client.return_value
    client.head_object.return_value = {"ContentLength": 0, "ContentType": "text/plain"}
    client.get_bucket_versioning.return_value = {"Status": "Enabled"}
    # 150 versions, all for the same key.
    many_versions = [
        {
            "Key": "k",
            "VersionId": f"v{i:03d}",
            "LastModified": "2026-01-01T00:00:00Z",
            "IsLatest": i == 0,
            "Size": 10,
        }
        for i in range(150)
    ]
    client.get_paginator.return_value.paginate.return_value = [
        {"Versions": many_versions, "DeleteMarkers": []},
    ]

    from awstui.models import TreeNode

    obj_node = TreeNode(
        id="s3:object:my-bucket:k",
        label="k",
        node_type="object",
        service="s3",
        expandable=False,
        metadata={"bucket_name": "my-bucket", "key": "k"},
    )

    plugin = S3Plugin()
    details = plugin.get_details(session, obj_node)
    versions = dict(details.summary_groups)["Versions"]
    # 100 actual version rows + one "..." row.
    assert len(versions) == 101
    assert "..." in versions
    assert "50" in versions["..."]  # 50 more omitted


def _object_node(key: str, bucket: str = "my-bucket"):
    from awstui.models import TreeNode

    return TreeNode(
        id=f"s3:object:{bucket}:{key}",
        label=key.rsplit("/", 1)[-1],
        node_type="object",
        service="s3",
        expandable=False,
        metadata={"bucket_name": bucket, "key": key},
    )


def test_has_content_true_for_objects_only():
    from awstui.models import TreeNode

    plugin = S3Plugin()
    obj = _object_node("readme.txt")
    bucket_node = TreeNode(
        id="s3:bucket:b",
        label="b",
        node_type="bucket",
        service="s3",
        expandable=True,
        metadata={"bucket_name": "b"},
    )
    assert plugin.has_content(obj) is True
    assert plugin.has_content(bucket_node) is False


def test_get_content_text_object():
    session = make_session()
    client = session.client.return_value
    client.head_object.return_value = {
        "ContentLength": 11,
        "ContentType": "text/plain",
    }
    body_mock = MagicMock()
    body_mock.read.return_value = b"hello world"
    client.get_object.return_value = {"Body": body_mock}

    plugin = S3Plugin()
    preview = plugin.get_content(session, _object_node("readme.txt"))

    assert preview is not None
    assert preview.kind == "text"
    assert preview.body == "hello world"
    assert preview.truncated is False
    # plain text has no lexer
    assert preview.language is None


def test_get_content_json_object_uses_json_lexer():
    session = make_session()
    client = session.client.return_value
    client.head_object.return_value = {
        "ContentLength": 13,
        "ContentType": "application/json",
    }
    body_mock = MagicMock()
    body_mock.read.return_value = b'{"hello": true}'
    client.get_object.return_value = {"Body": body_mock}

    plugin = S3Plugin()
    preview = plugin.get_content(session, _object_node("config.json"))

    assert preview.kind == "text"
    assert preview.language == "json"


def test_get_content_text_detected_by_extension_when_content_type_missing():
    session = make_session()
    client = session.client.return_value
    client.head_object.return_value = {
        "ContentLength": 4,
        "ContentType": "application/octet-stream",
    }
    body_mock = MagicMock()
    body_mock.read.return_value = b"abcd"
    client.get_object.return_value = {"Body": body_mock}

    plugin = S3Plugin()
    preview = plugin.get_content(session, _object_node("script.py"))

    assert preview.kind == "text"
    assert preview.language == "python"


def test_get_content_csv_extension_sets_csv_language():
    """CSV files — whether tagged text/csv, binary/octet-stream, or
    unlabelled — should surface language='csv' so the UI can render
    them with rainbow-csv column colouring."""
    session = make_session()
    client = session.client.return_value
    client.head_object.return_value = {
        "ContentLength": 11,
        "ContentType": "binary/octet-stream",
    }
    body_mock = MagicMock()
    body_mock.read.return_value = b"a,b,c\n1,2,3"
    client.get_object.return_value = {"Body": body_mock}

    plugin = S3Plugin()
    preview = plugin.get_content(session, _object_node("data.csv"))

    assert preview.language == "csv"


def test_get_content_binary_octet_stream_falls_back_to_extension():
    """S3 objects uploaded without a content-type sometimes come back as
    "binary/octet-stream" rather than the standard "application/octet-stream".
    Extension sniffing should kick in either way."""
    session = make_session()
    client = session.client.return_value
    client.head_object.return_value = {
        "ContentLength": 9,
        "ContentType": "binary/octet-stream",
    }
    body_mock = MagicMock()
    body_mock.read.return_value = b"a,b,c\n1,2,3"
    client.get_object.return_value = {"Body": body_mock}

    plugin = S3Plugin()
    preview = plugin.get_content(session, _object_node("data.csv"))

    assert preview.kind == "text"


def test_get_content_binary_object_returns_message_without_fetching():
    session = make_session()
    client = session.client.return_value
    client.head_object.return_value = {
        "ContentLength": 2048,
        "ContentType": "image/png",
    }

    plugin = S3Plugin()
    preview = plugin.get_content(session, _object_node("logo.png"))

    assert preview.kind == "binary"
    assert "image/png" in preview.body
    # get_object is NOT called for binary content.
    client.get_object.assert_not_called()


def test_get_content_truncates_large_text_objects():
    session = make_session()
    client = session.client.return_value
    size = 2_000_000
    client.head_object.return_value = {
        "ContentLength": size,
        "ContentType": "text/plain",
    }
    body_mock = MagicMock()
    body_mock.read.return_value = b"x" * 1_000_000
    client.get_object.return_value = {"Body": body_mock}

    plugin = S3Plugin()
    preview = plugin.get_content(session, _object_node("big.log"))

    assert preview.truncated is True
    assert preview.size == size
    # The client was asked for a byte range, not the whole object.
    call_kwargs = client.get_object.call_args.kwargs
    assert call_kwargs["Range"].startswith("bytes=0-")


def test_get_content_returns_none_for_non_object_node():
    from awstui.models import TreeNode

    plugin = S3Plugin()
    bucket_node = TreeNode(
        id="s3:bucket:b",
        label="b",
        node_type="bucket",
        service="s3",
        expandable=True,
        metadata={"bucket_name": "b"},
    )
    assert plugin.get_content(make_session(), bucket_node) is None
