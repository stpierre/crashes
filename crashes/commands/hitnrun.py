"""Find crashes near certain features."""

from crashes.commands import curate
from crashes import models


class Hitnrun(curate.Curate):
    """Determine who hit-and-ran."""

    results_column = "hit_and_run_status_name"
    status_table = models.HitAndRunStatus

    def _get_default(self, _):
        # not trying to be biased here, this is just a sensible default :(
        return "D"
