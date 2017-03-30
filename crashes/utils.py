"""Assorted utility functions."""

import os


def case_no_to_filename(case_no):
    return "%s.PDF" % case_no.replace("-", "").upper()


def filename_to_case_no(fpath):
    """Get the case number from a report filename."""
    case_id = os.path.splitext(os.path.basename(fpath))[0]
    return "%s-%s" % (case_id[0:2], case_id[2:])
