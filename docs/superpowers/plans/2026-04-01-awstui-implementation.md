# awstui Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a read-only TUI for browsing AWS resources using Textual, with a pluggable service architecture supporting S3, Lambda, RDS, IAM, SQS, and SNS.

**Architecture:** ABC-based plugin system where each AWS service implements `AWSServicePlugin`. A Textual app with a tree widget (left) for navigation and a tabbed detail pane (right). Lazy-loading of children on expand. Error handling wraps all boto3 calls.

**Tech Stack:** Python 3.12+, uv, Textual, boto3, pytest

---

## File Structure

| File | Responsibility |
|------|---------------|
| `pyproject.toml` | Project metadata, dependencies, entry point |
| `src/awstui/__init__.py` | Package marker |
| `src/awstui/__main__.py` | `python -m awstui` entry point |
| `src/awstui/models.py` | `TreeNode` and `ResourceDetails` dataclasses |
| `src/awstui/plugin.py` | `AWSServicePlugin` ABC and `PluginRegistry` |
| `src/awstui/app.py` | Textual `App` subclass, layout composition |
| `src/awstui/widgets/__init__.py` | Package marker |
| `src/awstui/widgets/nav_tree.py` | Navigation tree widget (left pane) |
| `src/awstui/widgets/detail_pane.py` | Detail pane with Summary/Raw JSON tabs (right pane) |
| `src/awstui/widgets/region_selector.py` | Region dropdown in header |
| `src/awstui/services/__init__.py` | Auto-discovery of service plugins |
| `src/awstui/services/s3.py` | S3 plugin |
| `src/awstui/services/lambda_.py` | Lambda plugin |
| `src/awstui/services/rds.py` | RDS plugin |
| `src/awstui/services/iam.py` | IAM plugin |
| `src/awstui/services/sqs.py` | SQS plugin |
| `src/awstui/services/sns.py` | SNS plugin |
| `tests/test_models.py` | Tests for dataclasses |
| `tests/test_plugin.py` | Tests for ABC and registry |
| `tests/test_services/test_s3.py` | S3 plugin tests |
| `tests/test_services/test_lambda.py` | Lambda plugin tests |
| `tests/test_services/test_rds.py` | RDS plugin tests |
| `tests/test_services/test_iam.py` | IAM plugin tests |
| `tests/test_services/test_sqs.py` | SQS plugin tests |
| `tests/test_services/test_sns.py` | SNS plugin tests |
| `tests/test_app.py` | App integration tests using Textual pilot |

---

### Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `src/awstui/__init__.py`
- Create: `src/awstui/__main__.py`

- [ ] **Step 1: Initialize uv project**

```bash
cd /Users/jamiethomson/github/jamiekt/awstui
uv init --lib --name awstui
```

This creates `pyproject.toml` and `src/awstui/__init__.py`. If uv generates a `hello.py` or similar sample file, delete it.

- [ ] **Step 2: Edit pyproject.toml**

Replace the generated `pyproject.toml` with:

```toml
[project]
name = "awstui"
version = "0.1.0"
description = "A TUI for browsing AWS resources"
requires-python = ">=3.12"
dependencies = [
    "textual>=3.0",
    "boto3>=1.35",
]

[project.scripts]
awstui = "awstui.__main__:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.25",
    "textual-dev>=1.7",
]
```

- [ ] **Step 3: Install dependencies**

```bash
uv sync
```

Expected: resolves and installs textual, boto3, and dev dependencies.

- [ ] **Step 4: Create __main__.py**

Create `src/awstui/__main__.py`:

```python
def main():
    from awstui.app import AWSBrowserApp

    app = AWSBrowserApp()
    app.run()


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Create placeholder app.py so imports work**

Create `src/awstui/app.py`:

```python
from textual.app import App


class AWSBrowserApp(App):
    """AWS TUI Browser - placeholder."""

    def compose(self):
        yield from []
```

- [ ] **Step 6: Verify the project runs**

```bash
uv run python -c "from awstui.app import AWSBrowserApp; print('OK')"
```

Expected: prints `OK`.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock src/
git commit -m "feat: scaffold project with uv, textual, boto3"
```

---

### Task 2: Models (TreeNode and ResourceDetails)

**Files:**
- Create: `src/awstui/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write failing tests for models**

Create `tests/test_models.py`:

```python
from awstui.models import TreeNode, ResourceDetails


def test_tree_node_creation():
    node = TreeNode(
        id="bucket:my-bucket",
        label="my-bucket",
        node_type="bucket",
        service="s3",
        expandable=True,
        metadata={"bucket_name": "my-bucket"},
    )
    assert node.id == "bucket:my-bucket"
    assert node.label == "my-bucket"
    assert node.node_type == "bucket"
    assert node.service == "s3"
    assert node.expandable is True
    assert node.metadata == {"bucket_name": "my-bucket"}


def test_tree_node_default_metadata():
    node = TreeNode(
        id="func:my-func",
        label="my-func",
        node_type="function",
        service="lambda",
        expandable=False,
    )
    assert node.metadata == {}


def test_resource_details_creation():
    details = ResourceDetails(
        title="S3 Bucket: my-bucket",
        subtitle="arn:aws:s3:::my-bucket",
        summary={"Name": "my-bucket", "Region": "us-east-1"},
        raw={"BucketName": "my-bucket"},
    )
    assert details.title == "S3 Bucket: my-bucket"
    assert details.subtitle == "arn:aws:s3:::my-bucket"
    assert details.summary == {"Name": "my-bucket", "Region": "us-east-1"}
    assert details.raw == {"BucketName": "my-bucket"}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_models.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'awstui.models'`

- [ ] **Step 3: Implement models**

Create `src/awstui/models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TreeNode:
    """Represents a node in the AWS resource navigation tree."""

    id: str
    label: str
    node_type: str
    service: str
    expandable: bool
    metadata: dict = field(default_factory=dict)


@dataclass
class ResourceDetails:
    """Details for display in the detail pane."""

    title: str
    subtitle: str
    summary: dict[str, str]
    raw: dict
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_models.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/awstui/models.py tests/test_models.py
git commit -m "feat: add TreeNode and ResourceDetails dataclasses"
```

---

### Task 3: Plugin ABC and Registry

**Files:**
- Create: `src/awstui/plugin.py`
- Create: `tests/test_plugin.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_plugin.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_plugin.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'awstui.plugin'`

- [ ] **Step 3: Implement plugin.py**

Create `src/awstui/plugin.py`:

```python
from __future__ import annotations

from abc import ABC, abstractmethod

import boto3

from awstui.models import ResourceDetails, TreeNode


class AWSServicePlugin(ABC):
    """Base class for all AWS service plugins."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Display name, e.g. 'S3', 'Lambda'."""

    @property
    @abstractmethod
    def service_name(self) -> str:
        """boto3 service name, e.g. 's3', 'lambda'."""

    @abstractmethod
    def get_root_nodes(self, session: boto3.Session) -> list[TreeNode]:
        """Return top-level resource nodes for this service."""

    @abstractmethod
    def get_children(self, session: boto3.Session, node: TreeNode) -> list[TreeNode]:
        """Return child nodes for the given node."""

    @abstractmethod
    def get_details(self, session: boto3.Session, node: TreeNode) -> ResourceDetails:
        """Return details for the given node."""


class PluginRegistry:
    """Registry for discovered service plugins."""

    def __init__(self):
        self._plugins: dict[str, AWSServicePlugin] = {}

    def register(self, plugin: AWSServicePlugin) -> None:
        self._plugins[plugin.service_name] = plugin

    def get(self, service_name: str) -> AWSServicePlugin | None:
        return self._plugins.get(service_name)

    def list_plugins(self) -> list[AWSServicePlugin]:
        return list(self._plugins.values())
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_plugin.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/awstui/plugin.py tests/test_plugin.py
git commit -m "feat: add AWSServicePlugin ABC and PluginRegistry"
```

---

### Task 4: Service Auto-Discovery

**Files:**
- Create: `src/awstui/services/__init__.py`
- Create: `tests/test_services/__init__.py`

- [ ] **Step 1: Create services package with auto-discovery**

Create `src/awstui/services/__init__.py`:

```python
"""AWS service plugins — auto-discovered on import."""

from __future__ import annotations

import importlib
import pkgutil

from awstui.plugin import PluginRegistry

registry = PluginRegistry()


def discover_plugins() -> PluginRegistry:
    """Import all modules in this package and register any that expose a `plugin` variable."""
    package = importlib.import_module(__name__)
    for _importer, module_name, _ispkg in pkgutil.iter_modules(package.__path__):
        module = importlib.import_module(f"{__name__}.{module_name}")
        if hasattr(module, "plugin"):
            registry.register(module.plugin)
    return registry
```

- [ ] **Step 2: Create tests directory**

```bash
mkdir -p tests/test_services
touch tests/test_services/__init__.py
```

- [ ] **Step 3: Commit**

```bash
git add src/awstui/services/__init__.py tests/test_services/__init__.py
git commit -m "feat: add service plugin auto-discovery"
```

---

### Task 5: S3 Plugin

**Files:**
- Create: `src/awstui/services/s3.py`
- Create: `tests/test_services/test_s3.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_services/test_s3.py`:

```python
from unittest.mock import MagicMock

from awstui.services.s3 import S3Plugin


def make_session():
    return MagicMock()


def test_s3_plugin_properties():
    plugin = S3Plugin()
    assert plugin.name == "S3"
    assert plugin.service_name == "s3"


def test_get_root_nodes_returns_buckets():
    session = make_session()
    client = session.client.return_value
    client.list_buckets.return_value = {
        "Buckets": [
            {"Name": "bucket-a", "CreationDate": "2026-01-01T00:00:00Z"},
            {"Name": "bucket-b", "CreationDate": "2026-01-02T00:00:00Z"},
        ]
    }

    plugin = S3Plugin()
    nodes = plugin.get_root_nodes(session)

    assert len(nodes) == 2
    assert nodes[0].label == "bucket-a"
    assert nodes[0].node_type == "bucket"
    assert nodes[0].expandable is True
    assert nodes[0].metadata["bucket_name"] == "bucket-a"


def test_get_children_of_bucket_lists_prefixes_and_objects():
    session = make_session()
    client = session.client.return_value
    client.list_objects_v2.return_value = {
        "CommonPrefixes": [{"Prefix": "logs/"}],
        "Contents": [{"Key": "readme.txt", "Size": 1024}],
    }

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
    client.list_objects_v2.return_value = {
        "CommonPrefixes": [],
        "Contents": [{"Key": "logs/app.log", "Size": 2048}],
    }

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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_services/test_s3.py -v
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement S3 plugin**

Create `src/awstui/services/s3.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_services/test_s3.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/awstui/services/s3.py tests/test_services/test_s3.py
git commit -m "feat: add S3 service plugin"
```

---

### Task 6: Lambda Plugin

**Files:**
- Create: `src/awstui/services/lambda_.py`
- Create: `tests/test_services/test_lambda.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_services/test_lambda.py`:

```python
from unittest.mock import MagicMock

from awstui.services.lambda_ import LambdaPlugin


def make_session():
    return MagicMock()


def test_lambda_plugin_properties():
    plugin = LambdaPlugin()
    assert plugin.name == "Lambda"
    assert plugin.service_name == "lambda"


def test_get_root_nodes_returns_functions():
    session = make_session()
    client = session.client.return_value
    client.get_paginator.return_value.paginate.return_value = [
        {
            "Functions": [
                {
                    "FunctionName": "my-func",
                    "FunctionArn": "arn:aws:lambda:us-east-1:123:function:my-func",
                    "Runtime": "python3.12",
                },
                {
                    "FunctionName": "other-func",
                    "FunctionArn": "arn:aws:lambda:us-east-1:123:function:other-func",
                    "Runtime": "nodejs20.x",
                },
            ]
        }
    ]

    plugin = LambdaPlugin()
    nodes = plugin.get_root_nodes(session)

    assert len(nodes) == 2
    assert nodes[0].label == "my-func"
    assert nodes[0].node_type == "function"
    assert nodes[0].expandable is False


def test_get_children_returns_empty():
    session = make_session()
    from awstui.models import TreeNode

    node = TreeNode(
        id="lambda:function:my-func",
        label="my-func",
        node_type="function",
        service="lambda",
        expandable=False,
    )

    plugin = LambdaPlugin()
    assert plugin.get_children(session, node) == []


def test_get_details_for_function():
    session = make_session()
    client = session.client.return_value
    func_config = {
        "FunctionName": "my-func",
        "FunctionArn": "arn:aws:lambda:us-east-1:123:function:my-func",
        "Runtime": "python3.12",
        "Handler": "index.handler",
        "CodeSize": 1234,
        "MemorySize": 128,
        "Timeout": 30,
        "LastModified": "2026-03-01T00:00:00Z",
        "Description": "My function",
    }
    client.get_function.return_value = {"Configuration": func_config}

    from awstui.models import TreeNode

    node = TreeNode(
        id="lambda:function:my-func",
        label="my-func",
        node_type="function",
        service="lambda",
        expandable=False,
        metadata={"function_name": "my-func"},
    )

    plugin = LambdaPlugin()
    details = plugin.get_details(session, node)

    assert details.title == "Lambda Function: my-func"
    assert "Runtime" in details.summary
    assert "Memory (MB)" in details.summary
    assert "Timeout (s)" in details.summary
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_services/test_lambda.py -v
```

Expected: FAIL

- [ ] **Step 3: Implement Lambda plugin**

Create `src/awstui/services/lambda_.py`:

```python
from __future__ import annotations

import boto3

from awstui.models import ResourceDetails, TreeNode
from awstui.plugin import AWSServicePlugin


class LambdaPlugin(AWSServicePlugin):
    @property
    def name(self) -> str:
        return "Lambda"

    @property
    def service_name(self) -> str:
        return "lambda"

    def get_root_nodes(self, session: boto3.Session) -> list[TreeNode]:
        client = session.client("lambda")
        paginator = client.get_paginator("list_functions")
        nodes: list[TreeNode] = []
        for page in paginator.paginate():
            for func in page.get("Functions", []):
                nodes.append(
                    TreeNode(
                        id=f"lambda:function:{func['FunctionName']}",
                        label=func["FunctionName"],
                        node_type="function",
                        service="lambda",
                        expandable=False,
                        metadata={"function_name": func["FunctionName"]},
                    )
                )
        return nodes

    def get_children(self, session: boto3.Session, node: TreeNode) -> list[TreeNode]:
        return []

    def get_details(self, session: boto3.Session, node: TreeNode) -> ResourceDetails:
        client = session.client("lambda")
        response = client.get_function(FunctionName=node.metadata["function_name"])
        config = response["Configuration"]
        return ResourceDetails(
            title=f"Lambda Function: {config['FunctionName']}",
            subtitle=config.get("FunctionArn", ""),
            summary={
                "Function Name": config["FunctionName"],
                "Runtime": config.get("Runtime", "N/A"),
                "Handler": config.get("Handler", ""),
                "Description": config.get("Description", ""),
                "Code Size": str(config.get("CodeSize", "")),
                "Memory (MB)": str(config.get("MemorySize", "")),
                "Timeout (s)": str(config.get("Timeout", "")),
                "Last Modified": config.get("LastModified", ""),
            },
            raw=response,
        )


plugin = LambdaPlugin()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_services/test_lambda.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/awstui/services/lambda_.py tests/test_services/test_lambda.py
git commit -m "feat: add Lambda service plugin"
```

---

### Task 7: RDS Plugin

**Files:**
- Create: `src/awstui/services/rds.py`
- Create: `tests/test_services/test_rds.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_services/test_rds.py`:

```python
from unittest.mock import MagicMock

from awstui.services.rds import RDSPlugin


def make_session():
    return MagicMock()


def test_rds_plugin_properties():
    plugin = RDSPlugin()
    assert plugin.name == "RDS"
    assert plugin.service_name == "rds"


def test_get_root_nodes_returns_categories():
    session = make_session()
    plugin = RDSPlugin()
    nodes = plugin.get_root_nodes(session)

    assert len(nodes) == 2
    labels = [n.label for n in nodes]
    assert "DB Instances" in labels
    assert "DB Clusters" in labels
    assert all(n.expandable for n in nodes)
    assert all(n.node_type == "category" for n in nodes)


def test_get_children_of_instances_category():
    session = make_session()
    client = session.client.return_value
    client.describe_db_instances.return_value = {
        "DBInstances": [
            {
                "DBInstanceIdentifier": "mydb",
                "DBInstanceClass": "db.t3.micro",
                "Engine": "postgres",
                "DBInstanceArn": "arn:aws:rds:us-east-1:123:db:mydb",
            }
        ]
    }

    from awstui.models import TreeNode

    category_node = TreeNode(
        id="rds:category:instances",
        label="DB Instances",
        node_type="category",
        service="rds",
        expandable=True,
        metadata={"category": "instances"},
    )

    plugin = RDSPlugin()
    children = plugin.get_children(session, category_node)

    assert len(children) == 1
    assert children[0].label == "mydb"
    assert children[0].node_type == "db_instance"
    assert children[0].expandable is False


def test_get_children_of_clusters_category():
    session = make_session()
    client = session.client.return_value
    client.describe_db_clusters.return_value = {
        "DBClusters": [
            {
                "DBClusterIdentifier": "mycluster",
                "Engine": "aurora-mysql",
                "DBClusterArn": "arn:aws:rds:us-east-1:123:cluster:mycluster",
            }
        ]
    }

    from awstui.models import TreeNode

    category_node = TreeNode(
        id="rds:category:clusters",
        label="DB Clusters",
        node_type="category",
        service="rds",
        expandable=True,
        metadata={"category": "clusters"},
    )

    plugin = RDSPlugin()
    children = plugin.get_children(session, category_node)

    assert len(children) == 1
    assert children[0].label == "mycluster"
    assert children[0].node_type == "db_cluster"


def test_get_details_for_instance():
    session = make_session()
    client = session.client.return_value
    instance_data = {
        "DBInstanceIdentifier": "mydb",
        "DBInstanceClass": "db.t3.micro",
        "Engine": "postgres",
        "EngineVersion": "15.4",
        "DBInstanceStatus": "available",
        "DBInstanceArn": "arn:aws:rds:us-east-1:123:db:mydb",
        "Endpoint": {"Address": "mydb.xxx.us-east-1.rds.amazonaws.com", "Port": 5432},
        "AllocatedStorage": 20,
    }
    client.describe_db_instances.return_value = {
        "DBInstances": [instance_data]
    }

    from awstui.models import TreeNode

    node = TreeNode(
        id="rds:instance:mydb",
        label="mydb",
        node_type="db_instance",
        service="rds",
        expandable=False,
        metadata={"db_instance_id": "mydb"},
    )

    plugin = RDSPlugin()
    details = plugin.get_details(session, node)

    assert details.title == "RDS Instance: mydb"
    assert "Engine" in details.summary
    assert "Status" in details.summary
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_services/test_rds.py -v
```

Expected: FAIL

- [ ] **Step 3: Implement RDS plugin**

Create `src/awstui/services/rds.py`:

```python
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

        if node.node_type == "category":
            return ResourceDetails(
                title=node.label,
                subtitle="Expand to see resources",
                summary={},
                raw={},
            )

        return ResourceDetails(title=node.label, subtitle="", summary={}, raw={})


plugin = RDSPlugin()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_services/test_rds.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/awstui/services/rds.py tests/test_services/test_rds.py
git commit -m "feat: add RDS service plugin"
```

---

### Task 8: IAM Plugin

**Files:**
- Create: `src/awstui/services/iam.py`
- Create: `tests/test_services/test_iam.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_services/test_iam.py`:

```python
from unittest.mock import MagicMock

from awstui.services.iam import IAMPlugin


def make_session():
    return MagicMock()


def test_iam_plugin_properties():
    plugin = IAMPlugin()
    assert plugin.name == "IAM"
    assert plugin.service_name == "iam"


def test_get_root_nodes_returns_categories():
    session = make_session()
    plugin = IAMPlugin()
    nodes = plugin.get_root_nodes(session)

    labels = [n.label for n in nodes]
    assert "Users" in labels
    assert "Roles" in labels
    assert "Policies" in labels
    assert "Groups" in labels
    assert all(n.node_type == "category" for n in nodes)


def test_get_children_of_users_category():
    session = make_session()
    client = session.client.return_value
    client.get_paginator.return_value.paginate.return_value = [
        {
            "Users": [
                {"UserName": "alice", "Arn": "arn:aws:iam::123:user/alice"},
                {"UserName": "bob", "Arn": "arn:aws:iam::123:user/bob"},
            ]
        }
    ]

    from awstui.models import TreeNode

    node = TreeNode(
        id="iam:category:users",
        label="Users",
        node_type="category",
        service="iam",
        expandable=True,
        metadata={"category": "users"},
    )

    plugin = IAMPlugin()
    children = plugin.get_children(session, node)

    assert len(children) == 2
    assert children[0].label == "alice"
    assert children[0].node_type == "user"
    assert children[0].expandable is True


def test_get_children_of_user_returns_subcategories():
    session = make_session()

    from awstui.models import TreeNode

    node = TreeNode(
        id="iam:user:alice",
        label="alice",
        node_type="user",
        service="iam",
        expandable=True,
        metadata={"user_name": "alice"},
    )

    plugin = IAMPlugin()
    children = plugin.get_children(session, node)

    labels = [c.label for c in children]
    assert "Attached Policies" in labels
    assert "Inline Policies" in labels
    assert "Access Keys" in labels


def test_get_children_of_user_attached_policies():
    session = make_session()
    client = session.client.return_value
    client.list_attached_user_policies.return_value = {
        "AttachedPolicies": [
            {"PolicyName": "ReadOnlyAccess", "PolicyArn": "arn:aws:iam::aws:policy/ReadOnlyAccess"}
        ]
    }

    from awstui.models import TreeNode

    node = TreeNode(
        id="iam:user:alice:attached_policies",
        label="Attached Policies",
        node_type="user_attached_policies",
        service="iam",
        expandable=True,
        metadata={"user_name": "alice"},
    )

    plugin = IAMPlugin()
    children = plugin.get_children(session, node)

    assert len(children) == 1
    assert children[0].label == "ReadOnlyAccess"
    assert children[0].expandable is False


def test_get_details_for_user():
    session = make_session()
    client = session.client.return_value
    user_data = {
        "UserName": "alice",
        "UserId": "AIDA123",
        "Arn": "arn:aws:iam::123:user/alice",
        "CreateDate": "2025-01-01T00:00:00Z",
    }
    client.get_user.return_value = {"User": user_data}

    from awstui.models import TreeNode

    node = TreeNode(
        id="iam:user:alice",
        label="alice",
        node_type="user",
        service="iam",
        expandable=True,
        metadata={"user_name": "alice"},
    )

    plugin = IAMPlugin()
    details = plugin.get_details(session, node)

    assert details.title == "IAM User: alice"
    assert "User Name" in details.summary
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_services/test_iam.py -v
```

Expected: FAIL

- [ ] **Step 3: Implement IAM plugin**

Create `src/awstui/services/iam.py`:

```python
from __future__ import annotations

import json

import boto3

from awstui.models import ResourceDetails, TreeNode
from awstui.plugin import AWSServicePlugin


class IAMPlugin(AWSServicePlugin):
    @property
    def name(self) -> str:
        return "IAM"

    @property
    def service_name(self) -> str:
        return "iam"

    def get_root_nodes(self, session: boto3.Session) -> list[TreeNode]:
        return [
            TreeNode(id="iam:category:users", label="Users", node_type="category", service="iam", expandable=True, metadata={"category": "users"}),
            TreeNode(id="iam:category:roles", label="Roles", node_type="category", service="iam", expandable=True, metadata={"category": "roles"}),
            TreeNode(id="iam:category:policies", label="Policies", node_type="category", service="iam", expandable=True, metadata={"category": "policies"}),
            TreeNode(id="iam:category:groups", label="Groups", node_type="category", service="iam", expandable=True, metadata={"category": "groups"}),
        ]

    def get_children(self, session: boto3.Session, node: TreeNode) -> list[TreeNode]:
        client = session.client("iam")

        if node.node_type == "category":
            return self._get_category_children(client, node)

        if node.node_type == "user":
            return self._get_user_subcategories(node)

        if node.node_type == "role":
            return self._get_role_subcategories(node)

        if node.node_type == "user_attached_policies":
            return self._get_user_attached_policies(client, node)

        if node.node_type == "user_inline_policies":
            return self._get_user_inline_policies(client, node)

        if node.node_type == "user_access_keys":
            return self._get_user_access_keys(client, node)

        if node.node_type == "role_attached_policies":
            return self._get_role_attached_policies(client, node)

        if node.node_type == "role_inline_policies":
            return self._get_role_inline_policies(client, node)

        if node.node_type == "role_trust_policy":
            return []

        return []

    def _get_category_children(self, client, node: TreeNode) -> list[TreeNode]:
        category = node.metadata["category"]

        if category == "users":
            paginator = client.get_paginator("list_users")
            nodes: list[TreeNode] = []
            for page in paginator.paginate():
                for user in page.get("Users", []):
                    nodes.append(TreeNode(
                        id=f"iam:user:{user['UserName']}",
                        label=user["UserName"],
                        node_type="user",
                        service="iam",
                        expandable=True,
                        metadata={"user_name": user["UserName"]},
                    ))
            return nodes

        if category == "roles":
            paginator = client.get_paginator("list_roles")
            nodes = []
            for page in paginator.paginate():
                for role in page.get("Roles", []):
                    nodes.append(TreeNode(
                        id=f"iam:role:{role['RoleName']}",
                        label=role["RoleName"],
                        node_type="role",
                        service="iam",
                        expandable=True,
                        metadata={"role_name": role["RoleName"]},
                    ))
            return nodes

        if category == "policies":
            paginator = client.get_paginator("list_policies")
            nodes = []
            for page in paginator.paginate(Scope="Local"):
                for policy in page.get("Policies", []):
                    nodes.append(TreeNode(
                        id=f"iam:policy:{policy['PolicyName']}",
                        label=policy["PolicyName"],
                        node_type="policy",
                        service="iam",
                        expandable=False,
                        metadata={"policy_arn": policy["Arn"]},
                    ))
            return nodes

        if category == "groups":
            paginator = client.get_paginator("list_groups")
            nodes = []
            for page in paginator.paginate():
                for group in page.get("Groups", []):
                    nodes.append(TreeNode(
                        id=f"iam:group:{group['GroupName']}",
                        label=group["GroupName"],
                        node_type="group",
                        service="iam",
                        expandable=False,
                        metadata={"group_name": group["GroupName"]},
                    ))
            return nodes

        return []

    def _get_user_subcategories(self, node: TreeNode) -> list[TreeNode]:
        user = node.metadata["user_name"]
        return [
            TreeNode(id=f"iam:user:{user}:attached_policies", label="Attached Policies", node_type="user_attached_policies", service="iam", expandable=True, metadata={"user_name": user}),
            TreeNode(id=f"iam:user:{user}:inline_policies", label="Inline Policies", node_type="user_inline_policies", service="iam", expandable=True, metadata={"user_name": user}),
            TreeNode(id=f"iam:user:{user}:access_keys", label="Access Keys", node_type="user_access_keys", service="iam", expandable=True, metadata={"user_name": user}),
        ]

    def _get_role_subcategories(self, node: TreeNode) -> list[TreeNode]:
        role = node.metadata["role_name"]
        return [
            TreeNode(id=f"iam:role:{role}:attached_policies", label="Attached Policies", node_type="role_attached_policies", service="iam", expandable=True, metadata={"role_name": role}),
            TreeNode(id=f"iam:role:{role}:inline_policies", label="Inline Policies", node_type="role_inline_policies", service="iam", expandable=True, metadata={"role_name": role}),
            TreeNode(id=f"iam:role:{role}:trust_policy", label="Trust Policy", node_type="role_trust_policy", service="iam", expandable=False, metadata={"role_name": role}),
        ]

    def _get_user_attached_policies(self, client, node: TreeNode) -> list[TreeNode]:
        response = client.list_attached_user_policies(UserName=node.metadata["user_name"])
        return [
            TreeNode(
                id=f"iam:attached_policy:{p['PolicyArn']}",
                label=p["PolicyName"],
                node_type="attached_policy",
                service="iam",
                expandable=False,
                metadata={"policy_arn": p["PolicyArn"]},
            )
            for p in response.get("AttachedPolicies", [])
        ]

    def _get_user_inline_policies(self, client, node: TreeNode) -> list[TreeNode]:
        response = client.list_user_policies(UserName=node.metadata["user_name"])
        return [
            TreeNode(
                id=f"iam:inline_policy:{node.metadata['user_name']}:{name}",
                label=name,
                node_type="user_inline_policy",
                service="iam",
                expandable=False,
                metadata={"user_name": node.metadata["user_name"], "policy_name": name},
            )
            for name in response.get("PolicyNames", [])
        ]

    def _get_user_access_keys(self, client, node: TreeNode) -> list[TreeNode]:
        response = client.list_access_keys(UserName=node.metadata["user_name"])
        return [
            TreeNode(
                id=f"iam:access_key:{key['AccessKeyId']}",
                label=key["AccessKeyId"],
                node_type="access_key",
                service="iam",
                expandable=False,
                metadata={"user_name": node.metadata["user_name"], "access_key_id": key["AccessKeyId"]},
            )
            for key in response.get("AccessKeyMetadata", [])
        ]

    def _get_role_attached_policies(self, client, node: TreeNode) -> list[TreeNode]:
        response = client.list_attached_role_policies(RoleName=node.metadata["role_name"])
        return [
            TreeNode(
                id=f"iam:attached_policy:{p['PolicyArn']}",
                label=p["PolicyName"],
                node_type="attached_policy",
                service="iam",
                expandable=False,
                metadata={"policy_arn": p["PolicyArn"]},
            )
            for p in response.get("AttachedPolicies", [])
        ]

    def _get_role_inline_policies(self, client, node: TreeNode) -> list[TreeNode]:
        response = client.list_role_policies(RoleName=node.metadata["role_name"])
        return [
            TreeNode(
                id=f"iam:inline_policy:{node.metadata['role_name']}:{name}",
                label=name,
                node_type="role_inline_policy",
                service="iam",
                expandable=False,
                metadata={"role_name": node.metadata["role_name"], "policy_name": name},
            )
            for name in response.get("PolicyNames", [])
        ]

    def get_details(self, session: boto3.Session, node: TreeNode) -> ResourceDetails:
        client = session.client("iam")

        if node.node_type == "user":
            response = client.get_user(UserName=node.metadata["user_name"])
            user = response["User"]
            return ResourceDetails(
                title=f"IAM User: {user['UserName']}",
                subtitle=user.get("Arn", ""),
                summary={
                    "User Name": user["UserName"],
                    "User ID": user.get("UserId", ""),
                    "ARN": user.get("Arn", ""),
                    "Created": str(user.get("CreateDate", "")),
                },
                raw=user,
            )

        if node.node_type == "role":
            response = client.get_role(RoleName=node.metadata["role_name"])
            role = response["Role"]
            return ResourceDetails(
                title=f"IAM Role: {role['RoleName']}",
                subtitle=role.get("Arn", ""),
                summary={
                    "Role Name": role["RoleName"],
                    "Role ID": role.get("RoleId", ""),
                    "ARN": role.get("Arn", ""),
                    "Created": str(role.get("CreateDate", "")),
                    "Description": role.get("Description", ""),
                    "Max Session (s)": str(role.get("MaxSessionDuration", "")),
                },
                raw=role,
            )

        if node.node_type == "policy":
            response = client.get_policy(PolicyArn=node.metadata["policy_arn"])
            policy = response["Policy"]
            return ResourceDetails(
                title=f"IAM Policy: {policy['PolicyName']}",
                subtitle=policy.get("Arn", ""),
                summary={
                    "Policy Name": policy["PolicyName"],
                    "ARN": policy.get("Arn", ""),
                    "Description": policy.get("Description", ""),
                    "Attachment Count": str(policy.get("AttachmentCount", 0)),
                    "Default Version": policy.get("DefaultVersionId", ""),
                    "Created": str(policy.get("CreateDate", "")),
                },
                raw=policy,
            )

        if node.node_type == "group":
            response = client.get_group(GroupName=node.metadata["group_name"])
            group = response["Group"]
            users = response.get("Users", [])
            return ResourceDetails(
                title=f"IAM Group: {group['GroupName']}",
                subtitle=group.get("Arn", ""),
                summary={
                    "Group Name": group["GroupName"],
                    "Group ID": group.get("GroupId", ""),
                    "ARN": group.get("Arn", ""),
                    "Created": str(group.get("CreateDate", "")),
                    "Members": ", ".join(u["UserName"] for u in users) or "None",
                },
                raw=response,
            )

        if node.node_type == "role_trust_policy":
            response = client.get_role(RoleName=node.metadata["role_name"])
            doc = response["Role"].get("AssumeRolePolicyDocument", {})
            return ResourceDetails(
                title=f"Trust Policy: {node.metadata['role_name']}",
                subtitle=f"IAM Role: {node.metadata['role_name']}",
                summary={"Policy Document": json.dumps(doc, indent=2)},
                raw=doc,
            )

        if node.node_type == "attached_policy":
            response = client.get_policy(PolicyArn=node.metadata["policy_arn"])
            policy = response["Policy"]
            return ResourceDetails(
                title=f"IAM Policy: {policy['PolicyName']}",
                subtitle=policy.get("Arn", ""),
                summary={
                    "Policy Name": policy["PolicyName"],
                    "ARN": policy.get("Arn", ""),
                    "Description": policy.get("Description", ""),
                },
                raw=policy,
            )

        if node.node_type == "user_inline_policy":
            response = client.get_user_policy(
                UserName=node.metadata["user_name"],
                PolicyName=node.metadata["policy_name"],
            )
            doc = response.get("PolicyDocument", {})
            return ResourceDetails(
                title=f"Inline Policy: {node.metadata['policy_name']}",
                subtitle=f"User: {node.metadata['user_name']}",
                summary={"Policy Document": json.dumps(doc, indent=2)},
                raw=response,
            )

        if node.node_type == "role_inline_policy":
            response = client.get_role_policy(
                RoleName=node.metadata["role_name"],
                PolicyName=node.metadata["policy_name"],
            )
            doc = response.get("PolicyDocument", {})
            return ResourceDetails(
                title=f"Inline Policy: {node.metadata['policy_name']}",
                subtitle=f"Role: {node.metadata['role_name']}",
                summary={"Policy Document": json.dumps(doc, indent=2)},
                raw=response,
            )

        if node.node_type == "access_key":
            return ResourceDetails(
                title=f"Access Key: {node.metadata['access_key_id']}",
                subtitle=f"User: {node.metadata['user_name']}",
                summary={
                    "Access Key ID": node.metadata["access_key_id"],
                    "User": node.metadata["user_name"],
                },
                raw={"AccessKeyId": node.metadata["access_key_id"]},
            )

        if node.node_type == "category":
            return ResourceDetails(
                title=node.label, subtitle="Expand to see resources", summary={}, raw={}
            )

        return ResourceDetails(title=node.label, subtitle="", summary={}, raw={})


plugin = IAMPlugin()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_services/test_iam.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/awstui/services/iam.py tests/test_services/test_iam.py
git commit -m "feat: add IAM service plugin"
```

---

### Task 9: SQS Plugin

**Files:**
- Create: `src/awstui/services/sqs.py`
- Create: `tests/test_services/test_sqs.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_services/test_sqs.py`:

```python
from unittest.mock import MagicMock

from awstui.services.sqs import SQSPlugin


def make_session():
    return MagicMock()


def test_sqs_plugin_properties():
    plugin = SQSPlugin()
    assert plugin.name == "SQS"
    assert plugin.service_name == "sqs"


def test_get_root_nodes_returns_queues():
    session = make_session()
    client = session.client.return_value
    client.list_queues.return_value = {
        "QueueUrls": [
            "https://sqs.us-east-1.amazonaws.com/123/my-queue",
            "https://sqs.us-east-1.amazonaws.com/123/other-queue",
        ]
    }

    plugin = SQSPlugin()
    nodes = plugin.get_root_nodes(session)

    assert len(nodes) == 2
    assert nodes[0].label == "my-queue"
    assert nodes[0].node_type == "queue"
    assert nodes[0].expandable is False


def test_get_root_nodes_empty():
    session = make_session()
    client = session.client.return_value
    client.list_queues.return_value = {}

    plugin = SQSPlugin()
    nodes = plugin.get_root_nodes(session)
    assert nodes == []


def test_get_children_returns_empty():
    session = make_session()
    from awstui.models import TreeNode

    node = TreeNode(
        id="sqs:queue:my-queue",
        label="my-queue",
        node_type="queue",
        service="sqs",
        expandable=False,
        metadata={"queue_url": "https://sqs.us-east-1.amazonaws.com/123/my-queue"},
    )

    plugin = SQSPlugin()
    assert plugin.get_children(session, node) == []


def test_get_details_for_queue():
    session = make_session()
    client = session.client.return_value
    client.get_queue_attributes.return_value = {
        "Attributes": {
            "QueueArn": "arn:aws:sqs:us-east-1:123:my-queue",
            "ApproximateNumberOfMessages": "5",
            "ApproximateNumberOfMessagesNotVisible": "2",
            "ApproximateNumberOfMessagesDelayed": "0",
            "VisibilityTimeout": "30",
            "CreatedTimestamp": "1700000000",
            "LastModifiedTimestamp": "1700000001",
            "RedrivePolicy": '{"deadLetterTargetArn":"arn:aws:sqs:us-east-1:123:my-dlq","maxReceiveCount":3}',
        }
    }

    from awstui.models import TreeNode

    node = TreeNode(
        id="sqs:queue:my-queue",
        label="my-queue",
        node_type="queue",
        service="sqs",
        expandable=False,
        metadata={"queue_url": "https://sqs.us-east-1.amazonaws.com/123/my-queue"},
    )

    plugin = SQSPlugin()
    details = plugin.get_details(session, node)

    assert details.title == "SQS Queue: my-queue"
    assert "Messages Available" in details.summary
    assert "Dead Letter Queue" in details.summary
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_services/test_sqs.py -v
```

Expected: FAIL

- [ ] **Step 3: Implement SQS plugin**

Create `src/awstui/services/sqs.py`:

```python
from __future__ import annotations

import json

import boto3

from awstui.models import ResourceDetails, TreeNode
from awstui.plugin import AWSServicePlugin


class SQSPlugin(AWSServicePlugin):
    @property
    def name(self) -> str:
        return "SQS"

    @property
    def service_name(self) -> str:
        return "sqs"

    def get_root_nodes(self, session: boto3.Session) -> list[TreeNode]:
        client = session.client("sqs")
        response = client.list_queues()
        urls = response.get("QueueUrls", [])
        return [
            TreeNode(
                id=f"sqs:queue:{url.rsplit('/', 1)[-1]}",
                label=url.rsplit("/", 1)[-1],
                node_type="queue",
                service="sqs",
                expandable=False,
                metadata={"queue_url": url},
            )
            for url in urls
        ]

    def get_children(self, session: boto3.Session, node: TreeNode) -> list[TreeNode]:
        return []

    def get_details(self, session: boto3.Session, node: TreeNode) -> ResourceDetails:
        client = session.client("sqs")
        queue_url = node.metadata["queue_url"]
        response = client.get_queue_attributes(
            QueueUrl=queue_url, AttributeNames=["All"]
        )
        attrs = response.get("Attributes", {})

        redrive = attrs.get("RedrivePolicy", "")
        dlq_info = ""
        if redrive:
            parsed = json.loads(redrive)
            dlq_arn = parsed.get("deadLetterTargetArn", "")
            max_receive = parsed.get("maxReceiveCount", "")
            dlq_info = f"{dlq_arn} (max receives: {max_receive})"

        return ResourceDetails(
            title=f"SQS Queue: {node.label}",
            subtitle=attrs.get("QueueArn", ""),
            summary={
                "Queue URL": queue_url,
                "ARN": attrs.get("QueueArn", ""),
                "Messages Available": attrs.get("ApproximateNumberOfMessages", "0"),
                "Messages In Flight": attrs.get("ApproximateNumberOfMessagesNotVisible", "0"),
                "Messages Delayed": attrs.get("ApproximateNumberOfMessagesDelayed", "0"),
                "Visibility Timeout": attrs.get("VisibilityTimeout", ""),
                "Dead Letter Queue": dlq_info or "None",
            },
            raw=attrs,
        )


plugin = SQSPlugin()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_services/test_sqs.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/awstui/services/sqs.py tests/test_services/test_sqs.py
git commit -m "feat: add SQS service plugin"
```

---

### Task 10: SNS Plugin

**Files:**
- Create: `src/awstui/services/sns.py`
- Create: `tests/test_services/test_sns.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_services/test_sns.py`:

```python
from unittest.mock import MagicMock

from awstui.services.sns import SNSPlugin


def make_session():
    return MagicMock()


def test_sns_plugin_properties():
    plugin = SNSPlugin()
    assert plugin.name == "SNS"
    assert plugin.service_name == "sns"


def test_get_root_nodes_returns_topics():
    session = make_session()
    client = session.client.return_value
    client.get_paginator.return_value.paginate.return_value = [
        {
            "Topics": [
                {"TopicArn": "arn:aws:sns:us-east-1:123:my-topic"},
                {"TopicArn": "arn:aws:sns:us-east-1:123:other-topic"},
            ]
        }
    ]

    plugin = SNSPlugin()
    nodes = plugin.get_root_nodes(session)

    assert len(nodes) == 2
    assert nodes[0].label == "my-topic"
    assert nodes[0].node_type == "topic"
    assert nodes[0].expandable is True


def test_get_children_of_topic_returns_subscriptions():
    session = make_session()
    client = session.client.return_value
    client.list_subscriptions_by_topic.return_value = {
        "Subscriptions": [
            {
                "SubscriptionArn": "arn:aws:sns:us-east-1:123:my-topic:sub1",
                "Protocol": "email",
                "Endpoint": "user@example.com",
            }
        ]
    }

    from awstui.models import TreeNode

    node = TreeNode(
        id="sns:topic:my-topic",
        label="my-topic",
        node_type="topic",
        service="sns",
        expandable=True,
        metadata={"topic_arn": "arn:aws:sns:us-east-1:123:my-topic"},
    )

    plugin = SNSPlugin()
    children = plugin.get_children(session, node)

    assert len(children) == 1
    assert children[0].label == "email: user@example.com"
    assert children[0].node_type == "subscription"
    assert children[0].expandable is False


def test_get_details_for_topic():
    session = make_session()
    client = session.client.return_value
    client.get_topic_attributes.return_value = {
        "Attributes": {
            "TopicArn": "arn:aws:sns:us-east-1:123:my-topic",
            "DisplayName": "My Topic",
            "SubscriptionsConfirmed": "3",
            "SubscriptionsPending": "1",
            "SubscriptionsDeleted": "0",
        }
    }

    from awstui.models import TreeNode

    node = TreeNode(
        id="sns:topic:my-topic",
        label="my-topic",
        node_type="topic",
        service="sns",
        expandable=True,
        metadata={"topic_arn": "arn:aws:sns:us-east-1:123:my-topic"},
    )

    plugin = SNSPlugin()
    details = plugin.get_details(session, node)

    assert details.title == "SNS Topic: my-topic"
    assert "Subscriptions Confirmed" in details.summary


def test_get_details_for_subscription():
    session = make_session()
    client = session.client.return_value
    client.get_subscription_attributes.return_value = {
        "Attributes": {
            "SubscriptionArn": "arn:aws:sns:us-east-1:123:my-topic:sub1",
            "Protocol": "email",
            "Endpoint": "user@example.com",
            "TopicArn": "arn:aws:sns:us-east-1:123:my-topic",
            "Owner": "123456789012",
        }
    }

    from awstui.models import TreeNode

    node = TreeNode(
        id="sns:sub:sub1",
        label="email: user@example.com",
        node_type="subscription",
        service="sns",
        expandable=False,
        metadata={"subscription_arn": "arn:aws:sns:us-east-1:123:my-topic:sub1"},
    )

    plugin = SNSPlugin()
    details = plugin.get_details(session, node)

    assert details.title == "SNS Subscription"
    assert "Protocol" in details.summary
    assert "Endpoint" in details.summary
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_services/test_sns.py -v
```

Expected: FAIL

- [ ] **Step 3: Implement SNS plugin**

Create `src/awstui/services/sns.py`:

```python
from __future__ import annotations

import boto3

from awstui.models import ResourceDetails, TreeNode
from awstui.plugin import AWSServicePlugin


class SNSPlugin(AWSServicePlugin):
    @property
    def name(self) -> str:
        return "SNS"

    @property
    def service_name(self) -> str:
        return "sns"

    def get_root_nodes(self, session: boto3.Session) -> list[TreeNode]:
        client = session.client("sns")
        paginator = client.get_paginator("list_topics")
        nodes: list[TreeNode] = []
        for page in paginator.paginate():
            for topic in page.get("Topics", []):
                arn = topic["TopicArn"]
                name = arn.rsplit(":", 1)[-1]
                nodes.append(
                    TreeNode(
                        id=f"sns:topic:{name}",
                        label=name,
                        node_type="topic",
                        service="sns",
                        expandable=True,
                        metadata={"topic_arn": arn},
                    )
                )
        return nodes

    def get_children(self, session: boto3.Session, node: TreeNode) -> list[TreeNode]:
        if node.node_type != "topic":
            return []

        client = session.client("sns")
        response = client.list_subscriptions_by_topic(
            TopicArn=node.metadata["topic_arn"]
        )
        return [
            TreeNode(
                id=f"sns:sub:{sub['SubscriptionArn'].rsplit(':', 1)[-1]}",
                label=f"{sub['Protocol']}: {sub['Endpoint']}",
                node_type="subscription",
                service="sns",
                expandable=False,
                metadata={"subscription_arn": sub["SubscriptionArn"]},
            )
            for sub in response.get("Subscriptions", [])
        ]

    def get_details(self, session: boto3.Session, node: TreeNode) -> ResourceDetails:
        client = session.client("sns")

        if node.node_type == "topic":
            response = client.get_topic_attributes(
                TopicArn=node.metadata["topic_arn"]
            )
            attrs = response.get("Attributes", {})
            return ResourceDetails(
                title=f"SNS Topic: {node.label}",
                subtitle=attrs.get("TopicArn", ""),
                summary={
                    "Topic ARN": attrs.get("TopicArn", ""),
                    "Display Name": attrs.get("DisplayName", ""),
                    "Subscriptions Confirmed": attrs.get("SubscriptionsConfirmed", "0"),
                    "Subscriptions Pending": attrs.get("SubscriptionsPending", "0"),
                    "Subscriptions Deleted": attrs.get("SubscriptionsDeleted", "0"),
                },
                raw=attrs,
            )

        if node.node_type == "subscription":
            response = client.get_subscription_attributes(
                SubscriptionArn=node.metadata["subscription_arn"]
            )
            attrs = response.get("Attributes", {})
            return ResourceDetails(
                title="SNS Subscription",
                subtitle=attrs.get("SubscriptionArn", ""),
                summary={
                    "Subscription ARN": attrs.get("SubscriptionArn", ""),
                    "Protocol": attrs.get("Protocol", ""),
                    "Endpoint": attrs.get("Endpoint", ""),
                    "Topic ARN": attrs.get("TopicArn", ""),
                    "Owner": attrs.get("Owner", ""),
                },
                raw=attrs,
            )

        return ResourceDetails(title=node.label, subtitle="", summary={}, raw={})


plugin = SNSPlugin()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_services/test_sns.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/awstui/services/sns.py tests/test_services/test_sns.py
git commit -m "feat: add SNS service plugin"
```

---

### Task 11: Navigation Tree Widget

**Files:**
- Create: `src/awstui/widgets/__init__.py`
- Create: `src/awstui/widgets/nav_tree.py`

- [ ] **Step 1: Create widgets package**

```bash
mkdir -p src/awstui/widgets
touch src/awstui/widgets/__init__.py
```

- [ ] **Step 2: Implement nav_tree.py**

Create `src/awstui/widgets/nav_tree.py`:

```python
from __future__ import annotations

from typing import Any

import boto3
from botocore.exceptions import ClientError
from textual.message import Message
from textual.widgets import Tree
from textual.widgets._tree import TreeNode as TextualTreeNode

from awstui.models import TreeNode
from awstui.plugin import AWSServicePlugin


class NodeSelected(Message):
    """Posted when a tree node is selected."""

    def __init__(self, node_data: TreeNode) -> None:
        super().__init__()
        self.node_data = node_data


class NodeError(Message):
    """Posted when loading a node fails."""

    def __init__(self, error_message: str) -> None:
        super().__init__()
        self.error_message = error_message


class AWSNavTree(Tree[TreeNode]):
    """Navigation tree for browsing AWS resources."""

    def __init__(self, session: boto3.Session, plugins: list[AWSServicePlugin]) -> None:
        super().__init__("AWS Services")
        self._session = session
        self._plugins: dict[str, AWSServicePlugin] = {p.service_name: p for p in plugins}

    @property
    def session(self) -> boto3.Session:
        return self._session

    @session.setter
    def session(self, value: boto3.Session) -> None:
        self._session = value

    def on_mount(self) -> None:
        self.root.expand()
        self._populate_services()

    def _populate_services(self) -> None:
        for plugin in self._plugins.values():
            service_node = self.root.add(
                plugin.name,
                data=TreeNode(
                    id=f"service:{plugin.service_name}",
                    label=plugin.name,
                    node_type="service",
                    service=plugin.service_name,
                    expandable=True,
                ),
            )
            service_node.allow_expand = True

    def on_tree_node_expanded(self, event: Tree.NodeExpanded[TreeNode]) -> None:
        node = event.node
        if node.data is None:
            return

        # Only load children if they haven't been loaded yet
        if node.children:
            return

        data: TreeNode = node.data
        plugin = self._plugins.get(data.service)
        if plugin is None:
            return

        try:
            if data.node_type == "service":
                children = plugin.get_root_nodes(self._session)
            else:
                children = plugin.get_children(self._session, data)

            for child in children:
                child_node = node.add(child.label, data=child)
                child_node.allow_expand = child.expandable
        except ClientError as e:
            error_code = e.response["Error"].get("Code", "")
            if error_code in ("AccessDenied", "AccessDeniedException", "UnauthorizedAccess"):
                self.post_message(NodeError(f"Access Denied: insufficient permissions to list {data.label}"))
            else:
                self.post_message(NodeError(f"Error loading {data.label}: {e}"))
        except Exception as e:
            self.post_message(NodeError(f"Error loading {data.label}: {e}"))

    def on_tree_node_selected(self, event: Tree.NodeSelected[TreeNode]) -> None:
        if event.node.data is not None:
            self.post_message(NodeSelected(event.node.data))

    def reset_tree(self) -> None:
        """Clear and repopulate the tree (e.g. after region switch)."""
        self.clear()
        self._populate_services()
```

- [ ] **Step 3: Commit**

```bash
git add src/awstui/widgets/
git commit -m "feat: add navigation tree widget"
```

---

### Task 12: Detail Pane Widget

**Files:**
- Create: `src/awstui/widgets/detail_pane.py`

- [ ] **Step 1: Implement detail_pane.py**

Create `src/awstui/widgets/detail_pane.py`:

```python
from __future__ import annotations

import json

from rich.syntax import Syntax
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static, TabbedContent, TabPane

from awstui.models import ResourceDetails


class DetailPane(Static):
    """Right pane showing details of the selected resource."""

    DEFAULT_CSS = """
    DetailPane {
        height: 100%;
        padding: 1;
    }
    .detail-title {
        text-style: bold;
        color: $accent;
        margin-bottom: 0;
    }
    .detail-subtitle {
        color: $text-muted;
        margin-bottom: 1;
    }
    .detail-error {
        color: $error;
        margin: 2;
    }
    .summary-row {
        margin-bottom: 0;
    }
    .summary-label {
        color: $text-muted;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("Select a resource to view details", id="detail-placeholder")

    def show_details(self, details: ResourceDetails) -> None:
        """Display resource details with Summary and Raw JSON tabs."""
        self.remove_children()

        self.mount(Static(details.title, classes="detail-title"))
        if details.subtitle:
            self.mount(Static(details.subtitle, classes="detail-subtitle"))

        tabbed = TabbedContent()
        self.mount(tabbed)

        summary_pane = TabPane("Summary", id="tab-summary")
        raw_pane = TabPane("Raw JSON", id="tab-raw")

        tabbed.add_pane(summary_pane)
        tabbed.add_pane(raw_pane)

        if details.summary:
            for label, value in details.summary.items():
                summary_pane.mount(
                    Static(
                        Text.assemble(
                            (f"{label}: ", "bold dim"),
                            (str(value), ""),
                        ),
                        classes="summary-row",
                    )
                )
        else:
            summary_pane.mount(Static("No summary available"))

        raw_json = json.dumps(details.raw, indent=2, default=str)
        raw_pane.mount(
            VerticalScroll(
                Static(Syntax(raw_json, "json", theme="monokai", line_numbers=False))
            )
        )

    def show_error(self, message: str) -> None:
        """Display an error message."""
        self.remove_children()
        self.mount(Static(message, classes="detail-error"))

    def show_placeholder(self) -> None:
        """Show the default placeholder."""
        self.remove_children()
        self.mount(Static("Select a resource to view details", id="detail-placeholder"))
```

- [ ] **Step 2: Commit**

```bash
git add src/awstui/widgets/detail_pane.py
git commit -m "feat: add detail pane widget with Summary/Raw tabs"
```

---

### Task 13: Region Selector Widget

**Files:**
- Create: `src/awstui/widgets/region_selector.py`

- [ ] **Step 1: Implement region_selector.py**

Create `src/awstui/widgets/region_selector.py`:

```python
from __future__ import annotations

from textual.message import Message
from textual.widgets import Select


AWS_REGIONS = [
    "us-east-1",
    "us-east-2",
    "us-west-1",
    "us-west-2",
    "af-south-1",
    "ap-east-1",
    "ap-south-1",
    "ap-south-2",
    "ap-southeast-1",
    "ap-southeast-2",
    "ap-southeast-3",
    "ap-northeast-1",
    "ap-northeast-2",
    "ap-northeast-3",
    "ca-central-1",
    "eu-central-1",
    "eu-central-2",
    "eu-west-1",
    "eu-west-2",
    "eu-west-3",
    "eu-south-1",
    "eu-south-2",
    "eu-north-1",
    "il-central-1",
    "me-south-1",
    "me-central-1",
    "sa-east-1",
]


class RegionChanged(Message):
    """Posted when the user selects a new region."""

    def __init__(self, region: str) -> None:
        super().__init__()
        self.region = region


class RegionSelector(Select[str]):
    """Dropdown for selecting an AWS region."""

    def __init__(self, current_region: str) -> None:
        options = [(r, r) for r in AWS_REGIONS]
        super().__init__(options, value=current_region, allow_blank=False)

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.value is not None:
            self.post_message(RegionChanged(str(event.value)))
```

- [ ] **Step 2: Commit**

```bash
git add src/awstui/widgets/region_selector.py
git commit -m "feat: add region selector widget"
```

---

### Task 14: Main App — Compose Layout and Wire Everything Together

**Files:**
- Modify: `src/awstui/app.py`
- Create: `tests/test_app.py`

- [ ] **Step 1: Implement the full app.py**

Replace `src/awstui/app.py` with:

```python
from __future__ import annotations

import json

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Static

from awstui.models import ResourceDetails
from awstui.services import discover_plugins
from awstui.widgets.detail_pane import DetailPane
from awstui.widgets.nav_tree import AWSNavTree, NodeError, NodeSelected
from awstui.widgets.region_selector import RegionChanged, RegionSelector


class AWSBrowserApp(App):
    """AWS TUI Browser."""

    TITLE = "awstui"
    CSS = """
    #main {
        height: 1fr;
    }
    #nav-pane {
        width: 1fr;
        max-width: 40;
        min-width: 25;
        border-right: solid $primary;
    }
    #detail-pane {
        width: 3fr;
    }
    #identity-bar {
        dock: top;
        height: 1;
        padding: 0 1;
        background: $surface;
        color: $text-muted;
    }
    #region-bar {
        dock: top;
        height: 3;
        padding: 0 1;
        background: $surface;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._session: boto3.Session | None = None
        self._identity: str = ""
        self._region: str = ""

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(self._identity, id="identity-bar")
        with Horizontal(id="main"):
            with Vertical(id="nav-pane"):
                yield RegionSelector(self._region)
                yield AWSNavTree(self._session, [])  # placeholder, replaced on_mount
            yield DetailPane(id="detail-pane")
        yield Footer()

    def on_mount(self) -> None:
        try:
            self._session = boto3.Session()
            self._region = self._session.region_name or "us-east-1"
        except NoCredentialsError:
            self.query_one("#detail-pane", DetailPane).show_error(
                "No AWS credentials found. Configure credentials and restart."
            )
            return

        # Fetch identity
        try:
            sts = self._session.client("sts")
            identity = sts.get_caller_identity()
            self._identity = identity.get("Arn", "Unknown")
        except (ClientError, Exception):
            self._identity = "Unknown (could not fetch identity)"

        self.query_one("#identity-bar", Static).update(self._identity)

        # Discover plugins and rebuild tree
        registry = discover_plugins()
        plugins = registry.list_plugins()

        nav_pane = self.query_one("#nav-pane", Vertical)
        # Remove placeholder tree and region selector
        nav_pane.remove_children()
        # Mount fresh widgets
        nav_pane.mount(RegionSelector(self._region))
        nav_pane.mount(AWSNavTree(self._session, plugins))

    def on_node_selected(self, message: NodeSelected) -> None:
        detail = self.query_one("#detail-pane", DetailPane)
        node_data = message.node_data
        plugin_registry = discover_plugins()
        plugin = plugin_registry.get(node_data.service)

        if plugin is None:
            detail.show_placeholder()
            return

        if node_data.node_type == "service":
            detail.show_details(
                ResourceDetails(
                    title=plugin.name,
                    subtitle=f"boto3 service: {plugin.service_name}",
                    summary={},
                    raw={},
                )
            )
            return

        try:
            details = plugin.get_details(self._session, node_data)
            detail.show_details(details)
        except ClientError as e:
            error_code = e.response["Error"].get("Code", "")
            if error_code in ("AccessDenied", "AccessDeniedException", "UnauthorizedAccess"):
                detail.show_error(f"Access Denied: insufficient permissions to view {node_data.label}")
            else:
                detail.show_error(f"Error loading details: {e}")
        except Exception as e:
            detail.show_error(f"Error loading details: {e}")

    def on_node_error(self, message: NodeError) -> None:
        self.query_one("#detail-pane", DetailPane).show_error(message.error_message)

    def on_region_changed(self, message: RegionChanged) -> None:
        if message.region == self._region:
            return

        self._region = message.region
        self._session = boto3.Session(region_name=self._region)

        # Reset the nav tree
        tree = self.query_one(AWSNavTree)
        tree.session = self._session
        tree.reset_tree()

        # Clear detail pane
        self.query_one("#detail-pane", DetailPane).show_placeholder()
```

- [ ] **Step 2: Write a basic app integration test**

Create `tests/test_app.py`:

```python
import pytest
from unittest.mock import patch, MagicMock

from awstui.app import AWSBrowserApp


@pytest.mark.asyncio
async def test_app_starts():
    """Test that the app can be instantiated and composed."""
    app = AWSBrowserApp()
    async with app.run_test(size=(120, 40)) as pilot:
        # App should start without crashing
        assert app.title == "awstui"
```

- [ ] **Step 3: Run the test**

```bash
uv run pytest tests/test_app.py -v
```

Expected: 1 passed (the app composes without crashing even without AWS credentials — it shows an error in the detail pane).

- [ ] **Step 4: Commit**

```bash
git add src/awstui/app.py tests/test_app.py
git commit -m "feat: wire up main app with nav tree, detail pane, and region selector"
```

---

### Task 15: Entry Point and Final Integration

**Files:**
- Modify: `src/awstui/__main__.py` (already created in Task 1)

- [ ] **Step 1: Verify the CLI entry point works**

```bash
uv run python -c "from awstui.app import AWSBrowserApp; print('imports OK')"
uv run python -c "from awstui.services import discover_plugins; r = discover_plugins(); print(f'{len(r.list_plugins())} plugins discovered')"
```

Expected: `imports OK` and `6 plugins discovered`.

- [ ] **Step 2: Run the full test suite**

```bash
uv run pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 3: Add .gitignore**

Create `.gitignore`:

```
__pycache__/
*.pyc
.venv/
dist/
*.egg-info/
.superpowers/
```

- [ ] **Step 4: Commit**

```bash
git add .gitignore
git commit -m "chore: add .gitignore"
```

- [ ] **Step 5: Verify the app launches**

```bash
uv run awstui
```

Expected: the TUI launches with the header, nav tree showing 6 services, and empty detail pane. Press `q` to quit.

- [ ] **Step 6: Final commit if any adjustments were needed**

```bash
git add -A
git commit -m "feat: complete awstui v0.1.0 — AWS TUI browser"
```
