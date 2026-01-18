import logging
import sys

import click

from crunchize.engine import CrunchizeEngine


def setup_logging(verbose: bool):
    """
    Configure logging based on verbosity.
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )


@click.group()
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose logging.")
def cli(verbose):
    """
    Crunchize: Ansible-inspired batch image processing framework.
    """
    setup_logging(verbose)


@cli.command()
@click.argument("playbook", type=click.Path(exists=True, dir_okay=False))
@click.option(
    "--dry-run",
    is_flag=True,
    help="Simulate execution without making changes.",
)
def run(playbook, dry_run):
    """
    Run a Crunchize playbook.

    PLAYBOOK is the path to the YAML playbook file.
    """
    logger = logging.getLogger("crunchize.cli")
    logger.info(f"Loading playbook: {playbook}")

    try:
        engine = CrunchizeEngine(playbook, dry_run=dry_run)
        engine.run()
    except Exception as e:
        logger.error(f"Execution failed: {e}")
        if logging.getLogger().isEnabledFor(logging.DEBUG):
            logger.exception("Traceback:")
        sys.exit(1)


if __name__ == "__main__":
    cli()
