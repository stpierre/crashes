"""Find crashes near certain features."""

from crashes.commands import curate
from crashes import db


class Hitnrun(curate.Curate):
    """Determine who hit-and-ran."""

    results_column = "hit_and_run_status"
    status_fixture = db.hit_and_run_status

    def _get_default(self, _):
        # not trying to be biased here, this is just a sensible default :(
        return "D"

    def curate_case(self, report):
        return (report.get("road_location") not in (None, 'not involved') and
                report.get("hit_and_run", False))
