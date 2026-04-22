# awstui

A read-only terminal UI for browsing AWS resources, built with [Textual](https://textual.textualize.io/) and [boto3](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html).

## Features

- Browse AWS resources in a tree-based navigation pane
- View resource details in a Summary or Raw JSON tab
- Switch regions on the fly
- Pluggable service architecture — easy to add new AWS services
- Graceful handling of permission errors

## Screenshots

![Start](https://raw.githubusercontent.com/jamiekt/awstui/main/docs/images/scr2.png)
![Tag summary](https://raw.githubusercontent.com/jamiekt/awstui/main/docs/images/scr1.png)

### Supported Services

S3, Lambda, RDS, IAM, SQS, SNS, Secrets Manager

## Installation

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

## Usage

```bash
uv run awstui
uv run awstui --profile my-profile       # use a specific AWS profile
```

Uses your existing AWS credentials (environment variables, `~/.aws/credentials`, SSO — whatever boto3 resolves). Pass `--profile`/`-p` to override the profile explicitly.

## Hotkeys

| Key | Action |
| --- | --- |
| `1` | Focus the region selector |
| `2` | Focus the navigation tree |
| `3` | Focus the detail pane |
| `c` | Copy the ARN of the selected resource to the clipboard |
| `r` | Copy the Raw JSON of the selected resource to the clipboard |

## Running Tests

```bash
uv run pytest tests/ -v
```
