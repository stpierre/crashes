"""Log utilities."""

import logging


def setup_logging(verbose, prefix=None, deconfigure=True, logger=None):
    """Configure logging according to the verbosity level."""
    logger = logger or logging.root
    if deconfigure:
        for handler in logger.handlers:
            logger.removeHandler(handler)
    stderr = logging.StreamHandler()
    level = logging.WARNING
    fmt = ["%(message)s"]
    if prefix:
        fmt.insert(0, prefix)
    requests_level = logging.WARN
    if verbose == 1:
        level = logging.INFO
    elif verbose > 1:
        level = logging.DEBUG
        requests_level = logging.INFO
        fmt.insert(0, "%(levelname)s")
        if verbose > 2:
            requests_level = logging.DEBUG
            fmt.insert(0, "%(asctime)s")
    stderr.setFormatter(logging.Formatter(": ".join(fmt)))
    logger.setLevel(level)
    logger.addHandler(stderr)
    logger.debug("Set verbose to %s", verbose)

    if logger == logging.root:
        # requests is very noisy, quiet it down
        req_log = logging.getLogger("requests")
        req_log.setLevel(requests_level)
        req_log.addHandler(stderr)
