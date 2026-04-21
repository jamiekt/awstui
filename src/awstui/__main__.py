def main():
    import argparse

    from awstui.app import AWSBrowserApp

    parser = argparse.ArgumentParser(
        prog="awstui",
        description="A read-only TUI for browsing AWS resources.",
    )
    parser.add_argument(
        "-p",
        "--profile",
        help="AWS profile name to use (overrides AWS_PROFILE / AWS_DEFAULT_PROFILE)",
    )
    args = parser.parse_args()

    app = AWSBrowserApp(profile=args.profile)
    app.run()


if __name__ == "__main__":
    main()
