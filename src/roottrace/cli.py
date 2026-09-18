"""
Command-line entry point for RootTrace's ingestion pipeline.

Running this configures logging (so logger.info/warning calls actually print),
builds the incident timeline from the mock data, and writes the result to
incident_timeline.json.
"""

import logging
from pathlib import Path

from roottrace.ingestion import build_incident_timeline
from roottrace.config import settings
logger = logging.getLogger(__name__)


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def main() -> None:
    configure_logging()
    timeline = build_incident_timeline(settings.logs_path, settings.deployments_path)

    settings.output_path.write_text(timeline.model_dump_json(indent=2))
    logger.info("Timeline written to %s", settings.output_path)


if __name__ == "__main__":
    main()