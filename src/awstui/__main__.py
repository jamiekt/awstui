def main():
    import argparse
    import sys

    from awstui.app import AWSBrowserApp
    from awstui.services import discover_plugins

    parser = argparse.ArgumentParser(
        prog="awstui",
        description="A read-only TUI for browsing AWS resources.",
    )
    parser.add_argument(
        "-p",
        "--profile",
        help="AWS profile name to use (overrides AWS_PROFILE / AWS_DEFAULT_PROFILE)",
    )
    parser.add_argument(
        "-s",
        "--service",
        action="append",
        dest="services",
        metavar="NAME",
        help=(
            "Only show this service in the navigation tree. May be passed "
            "multiple times. If omitted, all services are shown."
        ),
    )
    args = parser.parse_args()

    services: list[str] | None = None
    if args.services:
        registry = discover_plugins()
        available = {p.service_name: p.name for p in registry.list_plugins()}
        requested = [s.lower() for s in args.services]
        unknown = [s for s in requested if s not in available]
        if unknown:
            print(
                f"error: unknown service(s): {', '.join(unknown)}",
                file=sys.stderr,
            )
            print(
                f"available services: {', '.join(sorted(available))}",
                file=sys.stderr,
            )
            sys.exit(2)
        services = requested

    app = AWSBrowserApp(profile=args.profile, services=services)
    app.run()


if __name__ == "__main__":
    main()
