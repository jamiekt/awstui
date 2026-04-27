# awstui

A read-only terminal UI for browsing AWS resources, built with [Textual](https://textual.textualize.io/) and [boto3](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html).

## Features

- Browse AWS resources in a tree-based navigation pane
- View tags for selected resources
- View tag summary for collections of resources
- View resource details in a Summary or Raw JSON tab
- Switch regions on the fly
- Filter hotkey
- Copy URI hotkey (for S3 buckets and objects, ECR images)
- Copy ARN hotkey

## Screenshots

![Start](https://raw.githubusercontent.com/jamiekt/awstui/main/docs/images/scr2.png)
![Tag summary](https://raw.githubusercontent.com/jamiekt/awstui/main/docs/images/scr1.png)

### Supported Services

S3, Lambda, RDS, IAM, SQS, SNS, Secrets Manager, ECR

## Installation

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

## Usage

```bash
uv run awstui
uv run awstui --profile my-profile              # use a specific AWS profile
uv run awstui --service s3 --service lambda     # only show these services
```

Uses your existing AWS credentials (environment variables, `~/.aws/credentials`, SSO — whatever boto3 resolves). Pass `--profile`/`-p` to override the profile explicitly. Pass `--service`/`-s` one or more times to restrict which services appear in the navigation tree; omit it to show all services.

## Hotkeys

| Key | Action |
| --- | --- |
| `1` | Focus the region selector |
| `2` | Focus the navigation tree |
| `3` | Focus the detail pane |
| `a` | Copy the ARN of the selected resource to the clipboard |
| `u` | Copy the URI of the selected resource (S3 bucket/object, ECR image) |
| `r` | Copy the Raw JSON of the selected resource to the clipboard |
| `f` | Filter children of the highlighted node by substring (empty input clears) |
| `w` | Toggle word wrap in the Content tab (CSVs default to no-wrap, others to wrap) |

## Running Tests

```bash
uv run pytest tests/ -v
```
