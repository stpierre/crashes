"""Log utilities."""

import logging


def getLogger(name=None):
    if name == "__main__":
        name = "crashes.cli"
    return logging.getLogger(name)


def setup_logging(verbose, prefix=None, deconfigure=True):
    """Configure logging according to the verbosity level."""
    if deconfigure:
        for handler in logging.root.handlers:
            logging.root.removeHandler(handler)
    stderr = logging.StreamHandler()
    level = logging.WARNING
    fmt = ["%(message)s"]
    if prefix:
        fmt.insert(0, prefix)
    if verbose == 1:
        level = logging.INFO
        requests_level = logging.WARN
    elif verbose > 1:
        level = logging.DEBUG
        requests_level = logging.INFO
        fmt.insert(0, "%(levelname)s")
        if verbose > 2:
            requests_level = logging.DEBUG
            fmt.insert(0, "%(asctime)s")
    stderr.setFormatter(logging.Formatter(": ".join(fmt)))
    logging.root.setLevel(level)
    logging.root.addHandler(stderr)
    logging.root.debug("Set verbose to %s" % verbose)

    # requests is very noisy, quiet it down
    req_log = logging.getLogger("requests")
    req_log.setLevel(requests_level)
    req_log.addHandler(stderr)
