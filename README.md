# awstui

A read-only terminal UI for browsing AWS resources, built with [Textual](https://textual.textualize.io/) and [boto3](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html).

## Features

- Browse AWS resources in a tree-based navigation pane
- View resource details in a Summary or Raw JSON tab
- Switch regions on the fly
- Pluggable service architecture — easy to add new AWS services
- Graceful handling of permission errors

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

## Running Tests

```bash
uv run pytest tests/ -v
```
