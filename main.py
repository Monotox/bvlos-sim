"""Entry point for the bvlos-sim CLI."""

from adapters.cli import app, install_cancellation_handlers


def main() -> None:
    install_cancellation_handlers()
    app()


if __name__ == "__main__":
    main()
