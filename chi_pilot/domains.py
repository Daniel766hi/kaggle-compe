"""Work out which χ-Bench track a task instruction belongs to."""

from __future__ import annotations

import re

PA_PROVIDER = "pa_provider"
PA_UM = "pa_um"
CM = "cm"
UNKNOWN = "unknown"

# The instruction's tool table and namespace line name the role explicitly. These are the
# strongest signals, so they are checked before counting tool names.
_ROLE_MARKERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (CM, ("care-manager namespaces", "patient data & care-manager tools")),
    (PA_UM, ("payer namespaces", "case data & payer tools")),
    (PA_PROVIDER, ("provider namespaces", "patient data & provider tools")),
)

# Tool namespaces that only exist on one side.
_TOOL_MARKERS: dict[str, tuple[str, ...]] = {
    CM: ("cm_intake", "cm_chart", "cm_outreach", "cm_assessment", "cm_care_plan"),
    PA_UM: ("payer_intake_hub", "payer_letter_center", "triage.", "review.", "determination."),
    PA_PROVIDER: ("cases.create_from_order", "auth.submit_authorization", "forms.", "docs.", "chart."),
}


def detect_domain(instruction: str) -> str:
    text = instruction.lower()
    for domain, markers in _ROLE_MARKERS:
        if any(marker in text for marker in markers):
            return domain
    # The lookbehind keeps "chart." from matching inside "cm_chart.".
    counts = {
        domain: sum(len(re.findall(r"(?<![a-z_])" + re.escape(m), text)) for m in markers)
        for domain, markers in _TOOL_MARKERS.items()
    }
    best = max(counts, key=counts.get)
    return best if counts[best] > 0 else UNKNOWN
