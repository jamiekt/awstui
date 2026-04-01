# awstui — AWS TUI Browser Design Spec

## Overview

A read-only terminal UI (TUI) for browsing AWS resources, built with [Textual](https://textual.textualize.io/). Uses the user's existing AWS credentials. Supports a pluggable service architecture so new AWS services can be added incrementally.

Initial services: S3, Lambda, RDS, IAM, SQS, SNS.

## Layout

Three areas:

1. **Header bar** — app name, region selector (filterable dropdown), current AWS identity (from `sts:GetCallerIdentity`, fetched once at startup).
2. **Navigation pane (left)** — collapsible tree. Top-level nodes are AWS services. Expanding a service lazily fetches its resources via boto3. Further drill-down into child resources.
3. **Details pane (right)** — shows details for the selected tree node with two tabs:
   - **Summary** — curated key-value table with human-readable labels.
   - **Raw JSON** — full API response rendered as formatted JSON.

Children are fetched lazily on expand to keep startup fast and minimize API calls.

## Plugin Architecture

### ABC Contract

Each AWS service plugin lives in `src/awstui/services/` and implements:

```python
class AWSServicePlugin(ABC):
    @property
    def name(self) -> str:
        """Display name, e.g. 'S3', 'Lambda'."""

    @property
    def service_name(self) -> str:
        """boto3 service name, e.g. 's3', 'lambda'."""

    def get_root_nodes(self, session: boto3.Session) -> list[TreeNode]:
        """Top-level resources (e.g. list of buckets)."""

    def get_children(self, session: boto3.Session, node: TreeNode) -> list[TreeNode]:
        """Child resources for a given node."""

    def get_details(self, session: boto3.Session, node: TreeNode) -> ResourceDetails:
        """Fetch details for the selected node."""
```

### Data Types

```python
@dataclass
class TreeNode:
    id: str              # Unique identifier
    label: str           # Display text
    node_type: str       # e.g. "bucket", "object", "function"
    service: str         # Back-reference to service name
    expandable: bool     # Whether this node has children
    metadata: dict       # Context for child/detail fetches (e.g. bucket name)

@dataclass
class ResourceDetails:
    title: str                       # e.g. "S3 Bucket: my-bucket"
    subtitle: str                    # e.g. ARN or path
    summary: dict[str, str]          # Ordered label->value pairs for Summary tab
    raw: dict                        # Full API response for Raw JSON tab
```

### Discovery

`services/__init__.py` auto-imports all plugin modules in the package. Each module exposes a module-level `plugin` variable (an instance of the plugin class). The registry collects these at startup.

Adding a new service = create a new file in `services/`, implement the ABC, set `plugin = MyServicePlugin()`.

### Error Handling

Each `get_root_nodes`, `get_children`, and `get_details` call is wrapped by the calling code in a try/except that catches `botocore.exceptions.ClientError`. On access denied, an inline error message is shown in the details pane (e.g. "Access Denied: insufficient permissions to view this resource"). Other errors show a generic message with the exception text. The user can continue browsing other resources.

## Service Tree Structures

### S3
```
S3
└── <bucket>
    └── <prefix/object> (navigable like a filesystem)
```
`get_root_nodes` calls `list_buckets`. `get_children` on a bucket calls `list_objects_v2` with delimiter `/` to navigate prefix hierarchy.

### Lambda
```
Lambda
└── <function> (details only)
```
`get_root_nodes` calls `list_functions`. No children.

### RDS
```
RDS
├── DB Instances
│   └── <instance> (details only)
└── DB Clusters
    └── <cluster> (details only)
```
`get_root_nodes` returns two category nodes ("DB Instances", "DB Clusters"). `get_children` on each calls the respective `describe_*` API.

### IAM
```
IAM
├── Users
│   └── <user>
│       ├── Attached Policies
│       ├── Inline Policies
│       └── Access Keys
├── Roles
│   └── <role>
│       ├── Attached Policies
│       ├── Inline Policies
│       └── Trust Policy
├── Policies
│   └── <policy> (details only)
└── Groups
    └── <group> (details only)
```
`get_root_nodes` returns four category nodes. IAM is a global service — requests always go to `us-east-1` regardless of selected region.

### SQS
```
SQS
└── <queue> (details include dead-letter config)
```
`get_root_nodes` calls `list_queues`. No children — queue attributes and dead-letter config shown in details.

### SNS
```
SNS
└── <topic>
    └── <subscription>
```
`get_root_nodes` calls `list_topics`. `get_children` on a topic calls `list_subscriptions_by_topic`.

## Region Switching

- A `boto3.Session` is created at startup using the user's existing credentials and default region.
- The header contains a filterable region selector showing all standard AWS regions.
- Switching region: creates a new session, clears the tree back to collapsed service roots, discards cached data.
- Current identity (header) is fetched once at startup and does not change on region switch.
- Global services (IAM, S3 bucket listing) are unaffected by region switch at the top level, but region-specific details still use the session.

## Project Structure

```
awstui/
├── pyproject.toml
├── README.md
└── src/
    └── awstui/
        ├── __init__.py
        ├── __main__.py         # Entry point
        ├── app.py              # Textual App, screen layout
        ├── widgets/
        │   ├── __init__.py
        │   ├── nav_tree.py     # Left pane tree widget
        │   ├── detail_pane.py  # Right pane with Summary/Raw tabs
        │   └── region_selector.py
        ├── models.py           # TreeNode, ResourceDetails
        ├── plugin.py           # AWSServicePlugin ABC, registry
        └── services/
            ├── __init__.py     # Auto-discovery
            ├── s3.py
            ├── lambda_.py
            ├── rds.py
            ├── iam.py
            ├── sqs.py
            └── sns.py
```

## Dependencies

- `textual` — TUI framework
- `boto3` — AWS SDK
- `rich` — (bundled with textual) for JSON formatting in raw view

## Entry Point

- `python -m awstui`
- CLI command: `awstui` (via `[project.scripts]` in `pyproject.toml`)

## Testing

- Each plugin testable independently by mocking `boto3.Session`.
- App layer testable via Textual's pilot testing framework.
