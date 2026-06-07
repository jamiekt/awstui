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


def test_size_suffix_with_count():
    from awstui.app import _size_suffix

    # Container: size + count, with thousands separator and plural noun.
    assert _size_suffix(1024, done=True, count=3402) == " (1.0 KB, 3,402 objects)"
    assert _size_suffix(1024, done=False, count=1201) == " (⋯ 1.0 KB, 1,201 objects)"
    # Singular noun for exactly one object.
    assert _size_suffix(1024, done=True, count=1) == " (1.0 KB, 1 object)"
    # count=None -> size only (leaf objects).
    assert _size_suffix(1024, done=True, count=None) == " (1.0 KB)"


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
    # A container node (prefix) -> count is shown.
    node = _FakeNode("my-folder/", data=_node("prefix", bucket_name="b", prefix="f/"))
    app._size_base_labels[id(node)] = "my-folder/"

    app._set_node_size(node, 2048, done=False, count=5)
    assert node.label == "my-folder/ (⋯ 2.0 KB, 5 objects)"

    app._set_node_size(node, 2048, done=True, count=5)
    assert node.label == "my-folder/ (2.0 KB, 5 objects)"


def test_set_node_size_object_shows_size_only():
    app = AWSBrowserApp()
    # A leaf object -> count is suppressed (always 1).
    node = _FakeNode("file.txt", data=_node("object", bucket_name="b", key="file.txt"))
    app._size_base_labels[id(node)] = "file.txt"

    app._set_node_size(node, 2048, done=True, count=1)
    assert node.label == "file.txt (2.0 KB)"


def test_size_on_serves_cache_hit_without_worker():
    app = AWSBrowserApp()
    data = _node("prefix", bucket_name="b", prefix="logs/")
    data.id = "s3:prefix:b:logs/"
    node = _FakeNode("logs/", data=data)
    app._size_cache["s3:prefix:b:logs/"] = (2048, 5)

    app._size_on(node)

    # Completed total applied straight from cache; no worker spawned.
    assert node.label == "logs/ (2.0 KB, 5 objects)"
    assert app._size_base_labels[id(node)] == "logs/"
    assert id(node) not in app._size_workers


def test_size_on_cache_miss_spawns_worker(monkeypatch):
    app = AWSBrowserApp()
    data = _node("prefix", bucket_name="b", prefix="logs/")
    data.id = "s3:prefix:b:logs/"
    node = _FakeNode("logs/", data=data)

    spawned = []
    monkeypatch.setattr(
        app, "_size_worker", lambda n, d: spawned.append(n) or _FakeWorker()
    )

    app._size_on(node)

    assert spawned == [node]
    assert app._size_base_labels[id(node)] == "logs/"
    assert node.label == "logs/ (⋯)"


def test_size_on_container_under_inflight_ancestor_skips_worker(monkeypatch):
    """A prefix cascaded under an in-flight ancestor walk is fed by that
    walk — it registers but spawns no worker of its own."""
    app = AWSBrowserApp()

    parent_data = _node("bucket", bucket_name="b")
    parent_data.id = "s3:bucket:b"
    parent = _FakeNode("b", data=parent_data)
    # Parent is mid-walk: it has a live worker.
    app._size_base_labels[id(parent)] = "b"
    app._size_workers[id(parent)] = _FakeWorker()

    child_data = _node("prefix", bucket_name="b", prefix="logs/")
    child_data.id = "s3:prefix:b:logs/"
    child = _FakeNode("logs/", data=child_data)
    child.parent = parent
    parent.children = [child]

    spawned = []
    monkeypatch.setattr(
        app, "_size_worker", lambda n, d: spawned.append(n) or _FakeWorker()
    )

    app._size_on(child)

    assert spawned == []  # no redundant walk
    assert id(child) not in app._size_workers
    assert app._size_base_labels[id(child)] == "logs/"
    assert child.label == "logs/ (⋯)"


def test_size_on_object_under_inflight_ancestor_still_spawns_worker(monkeypatch):
    """An object leaf is never in a prefix breakdown, so it keeps its own
    (instant, metadata-based) worker even under a sizing ancestor."""
    app = AWSBrowserApp()

    parent_data = _node("prefix", bucket_name="b", prefix="logs/")
    parent_data.id = "s3:prefix:b:logs/"
    parent = _FakeNode("logs/", data=parent_data)
    app._size_base_labels[id(parent)] = "logs/"
    app._size_workers[id(parent)] = _FakeWorker()

    obj_data = _node("object", bucket_name="b", key="logs/a", size=10)
    obj_data.id = "s3:object:b:logs/a"
    obj = _FakeNode("a", data=obj_data)
    obj.parent = parent
    parent.children = [obj]

    spawned = []
    monkeypatch.setattr(
        app, "_size_worker", lambda n, d: spawned.append(n) or _FakeWorker()
    )

    app._size_on(obj)

    assert spawned == [obj]


def test_forget_size_worker_clears_in_flight_handle():
    """A completed walk drops its worker handle (the worker's `finally`
    calls this), so `_has_sizing_ancestor` reports in-flight, not ever-ran."""
    app = AWSBrowserApp()
    parent = _FakeNode("b")
    child = _FakeNode("logs/")
    child.parent = parent
    app._size_workers[id(parent)] = _FakeWorker()

    assert app._has_sizing_ancestor(child) is True
    app._forget_size_worker(id(parent))
    assert id(parent) not in app._size_workers
    assert app._has_sizing_ancestor(child) is False


def test_apply_size_progress_updates_root_and_descendants():
    """One walk's per-page breakdown drives the root and every sized
    descendant in lock-step; the cache is committed only when done."""
    app = AWSBrowserApp()

    root_data = _node("bucket", bucket_name="b")
    root_data.id = "s3:bucket:b"
    root = _FakeNode("b", data=root_data)

    child_data = _node("prefix", bucket_name="b", prefix="logs/")
    child_data.id = "s3:prefix:b:logs/"
    child = _FakeNode("logs/", data=child_data)
    child.parent = root
    root.children = [child]

    # Both registered as sized; child has no worker (fed by root walk).
    app._size_base_labels[id(root)] = "b"
    app._size_base_labels[id(child)] = "logs/"

    # Mid-walk page: climbing, cache untouched.
    app._apply_size_progress(root, 30, 2, {"s3:prefix:b:logs/": (30, 2)}, done=False)
    assert root.label == "b (⋯ 30 B, 2 objects)"
    assert child.label == "logs/ (⋯ 30 B, 2 objects)"
    assert app._size_cache == {}

    # Final page: done, cache committed.
    app._apply_size_progress(root, 50, 3, {"s3:prefix:b:logs/": (50, 3)}, done=True)
    assert root.label == "b (50 B, 3 objects)"
    assert child.label == "logs/ (50 B, 3 objects)"
    assert app._size_cache == {"s3:prefix:b:logs/": (50, 3)}


def test_set_node_size_noop_after_toggle_off():
    app = AWSBrowserApp()
    node = _FakeNode("my-folder/")
    # Not in _size_base_labels -> treated as toggled off; label untouched.
    app._set_node_size(node, 2048, done=True, count=3)
    assert node.label == "my-folder/"


def test_set_node_size_unavailable_appends_suffix():
    app = AWSBrowserApp()
    node = _FakeNode("my-folder/")
    app._size_base_labels[id(node)] = "my-folder/"

    app._set_node_size_unavailable(node)
    assert node.label == "my-folder/ (size unavailable)"


def test_set_node_size_unavailable_noop_after_toggle_off():
    app = AWSBrowserApp()
    node = _FakeNode("my-folder/")
    # Not tracked -> toggled off; label untouched.
    app._set_node_size_unavailable(node)
    assert node.label == "my-folder/"


def test_apply_size_progress_commits_cache_only_when_done():
    app = AWSBrowserApp()
    node = _FakeNode("b")
    app._size_base_labels[id(node)] = "b"  # node is tracked
    assert app._size_cache == {}

    # Mid-walk page does not commit to the cache.
    app._apply_size_progress(node, 100, 3, {"s3:prefix:b:logs/": (100, 3)}, done=False)
    assert app._size_cache == {}

    # Final page commits, merging without dropping unrelated entries.
    app._size_cache["s3:prefix:b:old/"] = (1, 1)
    app._apply_size_progress(node, 140, 4, {"s3:prefix:b:logs/": (100, 3)}, done=True)
    assert app._size_cache == {
        "s3:prefix:b:old/": (1, 1),
        "s3:prefix:b:logs/": (100, 3),
    }


def test_apply_size_progress_dropped_for_untracked_node():
    """A progress callback for a root no longer tracked (cancelled /
    region-switched between the page finishing and this callback running) is
    dropped, so it can't re-populate a just-cleared cache or label."""
    app = AWSBrowserApp()
    node = _FakeNode("b")
    # node is NOT in _size_base_labels -> treated as stale.
    app._apply_size_progress(node, 100, 3, {"s3:prefix:b:logs/": (100, 3)}, done=True)
    assert app._size_cache == {}
    assert node.label == "b"


def test_cache_hit_uses_real_get_children_node_id():
    """End-to-end id-contract check: a prefix breakdown from the real S3
    iter_size, committed to the cache, is found by _size_on under the id the
    real get_children mints for that prefix node — proving the two id
    formats agree (the cache silently never hits if they drift)."""
    from awstui.services.s3 import S3Plugin

    plugin = S3Plugin()
    session = MagicMock()
    client = session.client.return_value

    # iter_size paginates WITHOUT a delimiter (recursive); get_children
    # paginates WITH Delimiter="/". Route pages by that distinction.
    def paginate(**kwargs):
        if "Delimiter" in kwargs:
            return [{"CommonPrefixes": [{"Prefix": "logs/"}], "Contents": []}]
        return [
            {"Contents": [{"Key": "logs/a", "Size": 10}, {"Key": "logs/b", "Size": 20}]}
        ]

    client.get_paginator.return_value.paginate.side_effect = paginate
    client.get_bucket_versioning.return_value = {"Status": "Suspended"}

    bucket = TreeNode(
        id="s3:bucket:b",
        label="b",
        node_type="bucket",
        service="s3",
        expandable=True,
        metadata={"bucket_name": "b"},
    )

    # Real walk -> breakdown keyed by the prefix node-id.
    *_, (total, count, descendants) = list(plugin.iter_size(session, bucket))
    assert descendants == {"s3:prefix:b:logs/": (30, 2)}

    # Real get_children mints the child prefix node with its own id.
    children = plugin.get_children(session, bucket)
    child = next(c for c in children if c.node_type == "prefix")
    assert child.id == "s3:prefix:b:logs/"  # same string the breakdown used

    app = AWSBrowserApp()
    bucket_node = _FakeNode("b", data=bucket)
    app._size_base_labels[id(bucket_node)] = "b"  # tracked, so commit applies
    app._apply_size_progress(bucket_node, total, count, descendants, done=True)

    # _size_on on the real child node finds the cached total: no worker, done.
    child_node = _FakeNode("logs/", data=child)
    app._size_on(child_node)
    assert child_node.label == "logs/ (30 B, 2 objects)"
    assert id(child_node) not in app._size_workers


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


def test_cancel_all_sizes_clears_workers_and_labels():
    app = AWSBrowserApp()
    n1 = _FakeNode("a")
    n2 = _FakeNode("b")
    w1, w2 = _FakeWorker(), _FakeWorker()
    app._size_base_labels[id(n1)] = "a"
    app._size_base_labels[id(n2)] = "b"
    app._size_workers[id(n1)] = w1
    app._size_workers[id(n2)] = w2
    app._size_cache["s3:prefix:b:logs/"] = (10, 1)

    app._cancel_all_sizes()

    assert w1.cancelled and w2.cancelled
    assert app._size_base_labels == {}
    assert app._size_workers == {}
    assert app._size_cache == {}


@pytest.mark.asyncio
async def test_pressing_s_shows_size_in_label_end_to_end():
    """Press `s` on a bucket node and confirm the label gains a size.

    DetailPane.show_details mounts a TabbedContent and synchronously calls
    add_pane on it in the same frame; under the test pilot the TabbedContent
    isn't composed yet, so add_pane raises NoMatches(ContentTabs). That is a
    pre-existing harness limitation of the detail pane (reproducible on main,
    and never previously exercised because no pilot test selected a node) and
    is orthogonal to the size feature. We patch the detail-pane render to a
    no-op so this test exercises only the size path: key press -> action ->
    worker -> label update.
    """
    from awstui.models import TreeNode
    from awstui.plugin import AWSServicePlugin
    from awstui.widgets.detail_pane import DetailPane
    from awstui.widgets.nav_tree import AWSNavTree

    class FakeSizePlugin(AWSServicePlugin):
        @property
        def name(self):
            return "Fake"

        @property
        def service_name(self):
            return "fake"

        def get_root_nodes(self, session):
            return [
                TreeNode(
                    id="fake:bucket:b",
                    label="b",
                    node_type="bucket",
                    service="fake",
                    expandable=False,
                    metadata={"bucket_name": "b"},
                )
            ]

        def get_children(self, session, node):
            return []

        def get_details(self, session, node):
            from awstui.models import ResourceDetails

            return ResourceDetails(
                title="b", subtitle="s3://b", summary={"Name": "b"}, raw={}
            )

        def supports_size(self, node):
            return node.node_type == "bucket"

        def iter_size(self, session, node):
            yield 500, 1, {}
            yield 1024, 2, {}

    with (
        patch("awstui.app.boto3") as mock_boto3,
        patch.object(DetailPane, "show_details"),
        patch.object(DetailPane, "show_placeholder"),
    ):
        mock_session = MagicMock()
        mock_session.region_name = "us-east-1"
        mock_boto3.Session.return_value = mock_session

        app = AWSBrowserApp()
        async with app.run_test(size=(120, 40)) as pilot:
            # Replace discovered plugins with our fake, rebuild the tree.
            from awstui.plugin import PluginRegistry

            registry = PluginRegistry()
            registry.register(FakeSizePlugin())
            app._plugin_registry = registry
            app._session = mock_session

            tree = app.query_one(AWSNavTree)
            tree._plugins = {"fake": FakeSizePlugin()}
            tree.session = mock_session
            tree.reset_tree()
            await pilot.pause()

            # Expand the service node to reveal the bucket, select it.
            service_node = tree.root.children[0]
            service_node.expand()
            await pilot.pause()
            bucket_node = service_node.children[0]
            tree.focus()
            tree.select_node(bucket_node)
            await pilot.pause()

            await pilot.press("s")
            await app.workers.wait_for_complete()
            await pilot.pause()

            assert "1.0 KB, 2 objects" in str(bucket_node.label)
