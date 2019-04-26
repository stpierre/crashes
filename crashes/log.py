"""Log utilities."""

import logging


def setup_logging(verbose):
    """Configure logging according to the verbosity level."""
    if verbose > 2:
        # for high verbosity levels, configure the root logger to get stupid
        # amounts of logging from third-party modules
        logger = logging.getLogger()
    else:
        logger = logging.getLogger('crashes')

    stderr = logging.StreamHandler()
    level = logging.WARNING
    format_elements = ["%(levelname)s"]
    requests_level = logging.WARN
    if verbose == 1:
        level = logging.INFO
        format_elements.append("%(name)s")
    elif verbose > 1:
        level = logging.DEBUG
        requests_level = logging.INFO
        format_elements.append("(%(threadName)s)")
        if verbose > 2:
            requests_level = logging.DEBUG
            format_elements.insert(0, "%(asctime)s")
    if format_elements:
        log_fmt = " ".join(format_elements) + ": %(message)s"
    else:
        log_fmt = "%(message)s"
    stderr.setFormatter(logging.Formatter(log_fmt))

    logger.setLevel(level)
    logger.addHandler(stderr)
    logger.debug("Set verbose to %s", verbose)

    if logger == logging.root:
        # requests is very noisy, quiet it down
        req_log = logging.getLogger("requests")
        req_log.setLevel(requests_level)
        req_log.addHandler(stderr)
