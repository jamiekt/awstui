import boto3
from awstui.models import TreeNode, ResourceDetails
from awstui.plugin import AWSServicePlugin, PluginRegistry


class FakePlugin(AWSServicePlugin):
    @property
    def name(self) -> str:
        return "Fake"

    @property
    def service_name(self) -> str:
        return "fake"

    def get_root_nodes(self, session: boto3.Session) -> list[TreeNode]:
        return [
            TreeNode(
                id="fake:item1",
                label="Item 1",
                node_type="item",
                service="fake",
                expandable=False,
            )
        ]

    def get_children(self, session: boto3.Session, node: TreeNode) -> list[TreeNode]:
        return []

    def get_details(self, session: boto3.Session, node: TreeNode) -> ResourceDetails:
        return ResourceDetails(
            title="Fake Item",
            subtitle="fake:item1",
            summary={"Name": "Item 1"},
            raw={"name": "Item 1"},
        )


def test_plugin_implements_abc():
    plugin = FakePlugin()
    assert plugin.name == "Fake"
    assert plugin.service_name == "fake"


def test_registry_register_and_get():
    registry = PluginRegistry()
    plugin = FakePlugin()
    registry.register(plugin)
    assert registry.get("fake") is plugin


def test_registry_list_plugins():
    registry = PluginRegistry()
    plugin = FakePlugin()
    registry.register(plugin)
    plugins = registry.list_plugins()
    assert len(plugins) == 1
    assert plugins[0] is plugin


def test_registry_get_unknown_returns_none():
    registry = PluginRegistry()
    assert registry.get("unknown") is None


def test_cannot_instantiate_abc_directly():
    import pytest

    with pytest.raises(TypeError):
        AWSServicePlugin()
