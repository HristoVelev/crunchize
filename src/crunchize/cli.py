import logging
import sys

import click

from crunchize.engine import CrunchizeEngine


def setup_logging(verbose: bool):
    """
    Configure logging based on verbosity.
    """
    level = logging.DEBUG if verbose else logging.INFO

    # Custom factory to inject task context info into every log record
    old_factory = logging.getLogRecordFactory()

    def record_factory(*args, **kwargs):
        record = old_factory(*args, **kwargs)
        # Look for task context set by the engine in the logging module
        context = getattr(logging, "_crunchize_task_context", "")
        record.task_info = f" {context}" if context else ""
        return record

    logging.setLogRecordFactory(record_factory)

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s%(task_info)s: %(message)s",
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
@click.option(
    "--file-amount",
    type=click.FloatRange(0.0, 1.0),
    default=1.0,
    help="Relative amount of files to process (0.0 to 1.0).",
)
def run(playbook, dry_run, file_amount):
    """
    Run a Crunchize playbook.

    PLAYBOOK is the path to the YAML playbook file.
    """
    logger = logging.getLogger("crunchize.cli")
    try:
        engine = CrunchizeEngine(playbook, dry_run=dry_run, file_amount=file_amount)
        logger.info(f"Command: {' '.join(sys.argv)}")
        logger.info(f"Loading playbook: {playbook}")
        engine.run()
    except Exception as e:
        logger.error(f"Execution failed: {e}")
        if logging.getLogger().isEnabledFor(logging.DEBUG):
            logger.exception("Traceback:")
        sys.exit(1)


if __name__ == "__main__":
    cli()
