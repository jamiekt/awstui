import pytest
from unittest.mock import patch, MagicMock
from botocore.exceptions import NoCredentialsError

from awstui.app import AWSBrowserApp
from awstui.models import TreeNode


@pytest.mark.asyncio
async def test_app_starts():
    """Test that the app can be instantiated and composed."""
    # Mock boto3 to avoid AWS credential issues
    with patch("awstui.app.boto3") as mock_boto3:
        mock_session = MagicMock()
        mock_session.region_name = "us-east-1"
        mock_boto3.Session.side_effect = NoCredentialsError()

        app = AWSBrowserApp()
        async with app.run_test(size=(120, 40)):
            # App should start without crashing
            assert app.title == "awstui"


def test_find_arn_top_level():
    app = AWSBrowserApp()
    assert (
        app._find_arn({"Arn": "arn:aws:iam::123:user/alice"})
        == "arn:aws:iam::123:user/alice"
    )


def test_find_arn_service_specific_key():
    app = AWSBrowserApp()
    raw = {"QueueArn": "arn:aws:sqs:us-east-1:123:my-queue", "Other": "x"}
    assert app._find_arn(raw) == "arn:aws:sqs:us-east-1:123:my-queue"


def test_find_arn_nested():
    app = AWSBrowserApp()
    raw = {"Configuration": {"FunctionArn": "arn:aws:lambda:us-east-1:123:function:f"}}
    assert app._find_arn(raw) == "arn:aws:lambda:us-east-1:123:function:f"


def test_find_arn_uppercase_key():
    app = AWSBrowserApp()
    assert (
        app._find_arn({"ARN": "arn:aws:secretsmanager:us-east-1:123:secret:s"})
        == "arn:aws:secretsmanager:us-east-1:123:secret:s"
    )


def test_find_arn_ignores_non_arn_value():
    app = AWSBrowserApp()
    assert app._find_arn({"Arn": "not-an-arn"}) == ""


def test_find_arn_returns_empty_when_missing():
    app = AWSBrowserApp()
    assert app._find_arn({"Name": "foo", "Size": 42}) == ""


def test_find_arn_empty_input():
    app = AWSBrowserApp()
    assert app._find_arn({}) == ""


def test_noun_for_single_word():
    assert AWSBrowserApp._noun_for("Users") == "users"


def test_noun_for_multi_word():
    assert AWSBrowserApp._noun_for("DB Instances") == "instances"
    assert AWSBrowserApp._noun_for("Attached Policies") == "policies"
    assert AWSBrowserApp._noun_for("Access Keys") == "keys"


def test_noun_for_empty_label():
    assert AWSBrowserApp._noun_for("") == "items"
    assert AWSBrowserApp._noun_for("   ") == "items"


def test_pluralize_simple():
    assert AWSBrowserApp._pluralize("bucket") == "buckets"
    assert AWSBrowserApp._pluralize("function") == "functions"
    assert AWSBrowserApp._pluralize("queue") == "queues"
    assert AWSBrowserApp._pluralize("topic") == "topics"
    assert AWSBrowserApp._pluralize("secret") == "secrets"


def test_pluralize_sibilants():
    # keeps 'es' suffix behavior for words ending in s/x/z/ch/sh
    assert AWSBrowserApp._pluralize("box") == "boxes"


def test_pluralize_empty():
    assert AWSBrowserApp._pluralize("") == "items"


def _node(node_type: str, **metadata) -> TreeNode:
    return TreeNode(
        id="x",
        label="x",
        node_type=node_type,
        service="x",
        expandable=False,
        metadata=metadata,
    )


def test_uri_for_none_returns_empty():
    assert AWSBrowserApp._uri_for(None) == ""


def test_uri_for_s3_bucket():
    assert (
        AWSBrowserApp._uri_for(_node("bucket", bucket_name="my-bucket"))
        == "s3://my-bucket"
    )


def test_uri_for_s3_object():
    node = _node("object", bucket_name="my-bucket", key="path/to/file.txt")
    assert AWSBrowserApp._uri_for(node) == "s3://my-bucket/path/to/file.txt"


def test_uri_for_ecr_image_with_tag():
    node = _node(
        "private_image",
        repository_uri="123.dkr.ecr.us-east-1.amazonaws.com/my-app",
        image_digest="sha256:abc",
        image_tags=["latest", "v1"],
    )
    assert (
        AWSBrowserApp._uri_for(node)
        == "123.dkr.ecr.us-east-1.amazonaws.com/my-app:latest"
    )


def test_uri_for_ecr_image_without_tag_uses_digest():
    node = _node(
        "private_image",
        repository_uri="123.dkr.ecr.us-east-1.amazonaws.com/my-app",
        image_digest="sha256:abc",
        image_tags=[],
    )
    assert (
        AWSBrowserApp._uri_for(node)
        == "123.dkr.ecr.us-east-1.amazonaws.com/my-app@sha256:abc"
    )


def test_uri_for_public_ecr_image_with_tag():
    node = _node(
        "public_image",
        repository_uri="public.ecr.aws/123/public-app",
        image_digest="sha256:xyz",
        image_tags=["v2"],
    )
    assert AWSBrowserApp._uri_for(node) == "public.ecr.aws/123/public-app:v2"


def test_uri_for_unsupported_node_type_returns_empty():
    assert AWSBrowserApp._uri_for(_node("function", function_name="f")) == ""


def test_uri_for_s3_object_missing_metadata_returns_empty():
    assert AWSBrowserApp._uri_for(_node("object", bucket_name="b")) == ""


def test_uri_for_ecr_image_missing_repo_uri_returns_empty():
    node = _node("private_image", image_digest="sha256:abc", image_tags=["v1"])
    assert AWSBrowserApp._uri_for(node) == ""


def test_check_action_hides_copy_arn_when_no_arn():
    app = AWSBrowserApp()
    # Nothing selected
    assert app.check_action("copy_arn", ()) is False
    # Raw response with an ARN
    app._current_raw = {"RoleArn": "arn:aws:iam::123:role/r"}
    assert app.check_action("copy_arn", ()) is True
    # Subtitle-based ARN fallback
    app._current_raw = {}
    app._current_subtitle = "arn:aws:s3:::my-bucket"
    assert app.check_action("copy_arn", ()) is True


def test_check_action_hides_copy_uri_when_no_uri():
    app = AWSBrowserApp()
    assert app.check_action("copy_uri", ()) is False
    app._current_node = _node("bucket", bucket_name="my-bucket")
    assert app.check_action("copy_uri", ()) is True
    # Lambda functions don't have a URI -> still hidden
    app._current_node = _node("function", function_name="f")
    assert app.check_action("copy_uri", ()) is False


def test_check_action_hides_copy_raw_when_no_raw():
    app = AWSBrowserApp()
    assert app.check_action("copy_raw", ()) is False
    app._current_raw = {"something": 1}
    assert app.check_action("copy_raw", ()) is True


def test_check_action_passes_through_unrelated_actions():
    app = AWSBrowserApp()
    # Bindings we don't gate should stay visible.
    assert app.check_action("filter_children", ()) is True
    assert app.check_action("focus_nav", ()) is True


def test_services_defaults_to_none():
    app = AWSBrowserApp()
    assert app._services is None


def test_services_normalized_to_lowercase_set():
    app = AWSBrowserApp(services=["S3", "Lambda", "ECR"])
    assert app._services == {"s3", "lambda", "ecr"}


def test_empty_services_list_means_all():
    # Empty list is falsy, so the app treats it as "no filter".
    app = AWSBrowserApp(services=[])
    assert app._services is None


def test_escape_sql_doubles_single_quotes():
    from awstui.app import _escape_sql

    assert _escape_sql("plain") == "plain"
    assert _escape_sql("it's") == "it''s"
    assert _escape_sql("a'b'c") == "a''b''c"


def test_size_suffix_in_progress_and_done():
    from awstui.app import _size_suffix

    assert _size_suffix(1024, done=False) == " (⋯ 1.0 KB)"
    assert _size_suffix(1024, done=True) == " (1.0 KB)"


def test_check_action_hides_toggle_size_when_unsupported():
    from awstui.plugin import PluginRegistry
    from awstui.services.s3 import S3Plugin

    app = AWSBrowserApp()
    registry = PluginRegistry()
    registry.register(S3Plugin())
    app._plugin_registry = registry

    # Nothing selected -> hidden.
    assert app.check_action("toggle_size", ()) is False
    # A bucket -> shown.
    bucket_node = _node("bucket", bucket_name="b")
    bucket_node.service = "s3"
    app._current_node = bucket_node
    assert app.check_action("toggle_size", ()) is True
    # A category -> hidden.
    category_node = _node("category", category="general_purpose_buckets")
    category_node.service = "s3"
    app._current_node = category_node
    assert app.check_action("toggle_size", ()) is False


class _FakeNode:
    """Minimal stand-in for a Textual tree node for size-logic tests."""

    def __init__(self, label, data=None, children=None):
        self.label = label
        self.data = data
        self.children = children or []
        self.set_label_calls = []

    def set_label(self, label):
        self.label = label
        self.set_label_calls.append(label)


class _FakeWorker:
    def __init__(self):
        self.cancelled = False

    def cancel(self):
        self.cancelled = True


def test_set_node_size_updates_label_from_base():
    app = AWSBrowserApp()
    node = _FakeNode("my-folder/")
    app._size_base_labels[id(node)] = "my-folder/"

    app._set_node_size(node, 2048, done=False)
    assert node.label == "my-folder/ (⋯ 2.0 KB)"

    app._set_node_size(node, 2048, done=True)
    assert node.label == "my-folder/ (2.0 KB)"


def test_set_node_size_noop_after_toggle_off():
    app = AWSBrowserApp()
    node = _FakeNode("my-folder/")
    # Not in _size_base_labels -> treated as toggled off; label untouched.
    app._set_node_size(node, 2048, done=True)
    assert node.label == "my-folder/"


def test_cancel_size_restores_label_and_clears_state():
    app = AWSBrowserApp()
    node = _FakeNode("my-folder/ (⋯ 1.0 KB)")
    worker = _FakeWorker()
    app._size_base_labels[id(node)] = "my-folder/"
    app._size_workers[id(node)] = worker

    app._cancel_size(node)

    assert worker.cancelled is True
    assert node.label == "my-folder/"
    assert id(node) not in app._size_base_labels
    assert id(node) not in app._size_workers


def test_size_off_cascades_to_sized_descendants():
    app = AWSBrowserApp()
    grandchild = _FakeNode("gc")
    child = _FakeNode("c", children=[grandchild])
    parent = _FakeNode("p", children=[child])

    for n in (parent, child, grandchild):
        app._size_base_labels[id(n)] = n.label
        app._size_workers[id(n)] = _FakeWorker()

    app._size_off(parent)

    # All three turned off.
    for n in (parent, child, grandchild):
        assert id(n) not in app._size_base_labels
        assert id(n) not in app._size_workers


def test_expand_cascade_sizes_supported_children(monkeypatch):
    from awstui.plugin import PluginRegistry
    from awstui.services.s3 import S3Plugin

    app = AWSBrowserApp()
    registry = PluginRegistry()
    registry.register(S3Plugin())
    app._plugin_registry = registry

    # Record _size_on calls instead of spawning real workers.
    started = []
    monkeypatch.setattr(app, "_size_on", lambda node: started.append(node))

    prefix_data = _node("prefix", bucket_name="b", prefix="logs/")
    prefix_data.service = "s3"
    object_data = _node("object", bucket_name="b", key="logs/a", size=1)
    object_data.service = "s3"
    version_data = _node("object_version", bucket_name="b", key="logs/a")
    version_data.service = "s3"

    child_prefix = _FakeNode("logs/", data=prefix_data)
    child_object = _FakeNode("a", data=object_data)
    child_version = _FakeNode("v1", data=version_data)  # unsupported
    parent_data = _node("bucket", bucket_name="b")
    parent_data.service = "s3"
    parent = _FakeNode(
        "b",
        data=parent_data,
        children=[child_prefix, child_object, child_version],
    )
    # Parent is currently sized.
    app._size_base_labels[id(parent)] = "b"

    class _Event:
        node = parent

    app.on_tree_node_expanded(_Event())

    # Supported children cascade; the object_version child does not.
    assert child_prefix in started
    assert child_object in started
    assert child_version not in started


def test_expand_cascade_noop_when_parent_not_sized(monkeypatch):
    app = AWSBrowserApp()
    started = []
    monkeypatch.setattr(app, "_size_on", lambda node: started.append(node))

    parent = _FakeNode("b", children=[_FakeNode("c", data=_node("prefix"))])

    class _Event:
        node = parent

    app.on_tree_node_expanded(_Event())
    assert started == []
