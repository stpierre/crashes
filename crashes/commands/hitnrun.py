"""Find crashes near certain features."""

import json
import operator

from crashes.commands import curate
from crashes import log

LOG = log.getLogger(__name__)


class Hitnrun(curate.Curate):
    """Determine who hit-and-ran."""

    prerequisites = [curate.Curate]

    statuses = curate.StatusDict()
    statuses["D"] = curate.CurationStatus(
        "driver", "Driver only left scene")
    statuses["C"] = curate.CurationStatus(
        "cyclist", "Cyclist only left scene")
    statuses["2"] = curate.CurationStatus(
        "both", "Both driver and cyclist left the scene")
    statuses["N"] = curate.CurationStatus(
        "unclear", "Not a hit-and-run/unclear who left")

    results_file = "hitnrun_data"

    def _load_data(self):
        super(Hitnrun, self)._load_data()

        curation_data = json.load(open(self.options.curation_results))
        del curation_data["not_involved"]
        del curation_data["unknown"]
        relevant = reduce(operator.add, curation_data.values())

        metadata = json.load(open(self.options.metadata))
        relevant = [case_no for case_no in relevant
                    if metadata[case_no]["hit_and_run"]]

        self.data = {case_no: report for case_no, report in self.data.items()
                     if case_no in relevant}

    def _get_default(self, _):
        # not trying to be biased here, this is just a sensible default :(
        return "D"
