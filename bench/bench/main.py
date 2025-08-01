import logging
from pathlib import Path

import fire

from .bench import Bench

FORMAT = "%(asctime)s %(levelname)-8s %(name)-15s %(message)s"
LOGGER = logging.getLogger(__name__)


def main():
    logging.basicConfig(level=logging.INFO, format=FORMAT)
    # print current woking directory
    LOGGER.info(f"Current working directory: {Path.cwd()}")
    fire.Fire(Bench)
