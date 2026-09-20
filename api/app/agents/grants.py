"""Grant evidence review using the shared bounded snapshot runtime, not a new service."""

from hashlib import sha256

from .. import db
from . import cfo


INSTRUCTIONS = """
You are Sherlock's Grants & Compliance agent, a restricted-funds investigator for education systems.
Review uploaded award terms, grant registers, payroll charges, service evidence and relevant ledger support.
Never infer an award's rules from general knowledge, another award, or an institution's name. No web/legal
research is available. Identify which supplied terms apply; if that link is unclear request clarification.
Missing terms or service records mean needs_evidence, not noncompliance. An available document is not missing.
Payroll service_start/service_end fields prove dates only, NOT actual duties, time-and-effort or service
allocation. A within-window check cannot satisfy a requirement for actual service records. Inspect the source
inventory for separate service/allocation support (including relevant document sources). If none is supplied,
explicitly request service evidence and keep allocation support needs_evidence, even when dates and ceiling
checks pass. Do not conflate a timing clearance with documentation or allocation clearance.
Call check_grant for each award you discuss when normalized award/payroll records exist. Its exact integer-cent
totals cover ONLY supplied payroll charges, not lifetime expenditure, available funding, recoverable cash or
allowable cost. Do not add ledger amounts to payroll: these may represent the same economic event.
Service-period comparisons are mechanical signals, not legal eligibility decisions; pay date alone is not the
service period. A partial overlap does not determine an allocable amount. Do not calculate allocation deltas
or assume an account is a grant-eligible expense. Do not certify compliance, substantiate a violation, approve
an adjustment or issue an audit opinion. Describe evidence conflicts as hypotheses pending independent review.
Ground every finding in exact original source lines when available. State unreviewed awards and documents.
Propose follow-up for Payroll & Budget or Internal Auditor where useful, but do not claim they already ran.
In a synthetic workspace, assess consistency WITHIN the fictional scenario; the synthetic label itself is
not an exception and is not a reason to request private real-world records. Still label all conclusions unreviewed.
Compare full-cost grant charges with service/allocation evidence and explain any mismatch without inventing
a quantified adjustment. Request only supporting evidence genuinely needed for that question.
Use evidence-request role policy for award terms, allocation policies or award instructions; grants is for
structured grant-register CSV records. Service records use service; payroll-register CSV records use payroll.
Use submit_grants_analysis to finish. Keep the briefing concise and prefer evidence requests over speculation.
"""


def _display(cents):
    return f"{cents // 100:,}.{cents % 100:02}"


def _reference(record):
    return {"record_id": record["id"], "source_id": record["source_id"], "line": record["locator"]}


class GrantsTools(cfo.SnapshotTools):
    agent = "grants_compliance"
    label = "Grants & Compliance agent"
    submission_tool = "submit_grants_analysis"

    def __init__(self, ws):
        super().__init__(ws)
        self.checked_awards = set()

    def validate_result(self, result):
        errors = super().validate_result(result)
        if (self._records("grants") or self._records("payroll")) and not self.checked_awards:
            errors.append("Call check_grant for an award present in the normalized grant or payroll records before submitting.")
        return errors

    def instructions(self):
        # Keep the shared injection, citation, unit and execution-budget boundaries.
        return cfo.INSTRUCTIONS.replace("CFO triage agent", "Grants & Compliance agent").replace(
            "submit_cfo_analysis", self.submission_tool) + INSTRUCTIONS

    def tool_definitions(self):
        definitions = cfo._tools()
        definitions[-1] = {**definitions[-1], "name": self.submission_tool,
                           "description": "Submit unreviewed grant observations, evidence gaps and follow-up tasks."}
        definitions.insert(-1, cfo._tool(
            "check_grant", "Deterministic supplied-payroll totals and service-period checks for one award; not total grant expenditure or compliance.",
            {"award_id": {"type": "string", "minLength": 1, "maxLength": 200}}, ["award_id"]))
        return definitions

    def dispatch(self, name, args):
        if name == "check_grant":
            definition = next(t for t in self.tool_definitions() if t["name"] == name)
            cfo.validate_json(args, definition["parameters"])
            return self.check_grant(args["award_id"])
        return super().dispatch(name, args)

    def context(self):
        result = super().context()
        ids = sorted({r["payload"]["award_id"] for role in ("grants", "payroll") for r in self._records(role)})
        result.update({"award_ids": ids[:100], "award_count": len(ids), "award_ids_truncated": len(ids) > 100,
                       "grant_scope": "Only supplied records. Follow list_records pagination for additional awards. Award terms must be linked by evidence, not guessed."})
        return result

    def check_grant(self, award_id):
        awards = [r for r in self._records("grants") if r["payload"]["award_id"] == award_id]
        payroll = [r for r in self._records("payroll") if r["payload"]["award_id"] == award_id]
        if awards or payroll:
            self.checked_awards.add(award_id)
        # Distinct source systems can legitimately publish conflicting award definitions.
        # Do not choose one or add ceilings together.
        award = awards[0]["payload"] if len(awards) == 1 else None
        total = sum(r["payload"]["award_amount_cents"] for r in payroll)
        self.allowed_amounts.add(total)
        ceiling = award["ceiling_cents"] if award else None
        if ceiling is not None:
            self.allowed_amounts.add(ceiling)
        checks, counts = [], {"within": 0, "outside": 0, "overlaps": 0, "unknown": 0}
        for row in payroll:
            p = row["payload"]
            state = "unknown"
            if award:
                if p["service_end"] < award["valid_from"] or p["service_start"] > award["valid_to"]:
                    state = "outside"
                elif p["service_start"] >= award["valid_from"] and p["service_end"] <= award["valid_to"]:
                    state = "within"
                else:
                    state = "overlaps"
            counts[state] += 1
            if len(checks) < 40:
                checks.append({**_reference(row), "service_start": p["service_start"], "service_end": p["service_end"],
                               "window": state, "full_payroll_cost_charged": p["award_amount_cents"] == p["gross_cents"] + p["employer_cost_cents"]})
        inputs = sorted(r["id"] for r in awards + payroll)
        return {"calculation": "supplied_payroll_grant_check_v1", "snapshot_id": self.snapshot_id,
                "award_id": award_id, "award_status": "found" if award else "ambiguous" if awards else "missing",
                "award_references": [_reference(r) for r in awards[:20]], "award_record_count": len(awards),
                "valid_from": award["valid_from"] if award else None, "valid_to": award["valid_to"] if award else None,
                "currency": self.workspace["currency"], "payroll_record_count": len(payroll),
                "payroll_award_total_cents": total, "payroll_award_total_display": _display(total),
                "ceiling_cents": ceiling, "ceiling_display": _display(ceiling) if ceiling is not None else None,
                "recorded_payroll_exceeds_ceiling": total > ceiling if ceiling is not None and payroll else None,
                "service_period_counts": counts, "service_period_checks": checks,
                "checks_truncated": len(payroll) > len(checks),
                "input_record_ids_hash": sha256(db.encode(inputs).encode()).hexdigest(),
                "limitations": ["Payroll-only subset, not lifetime grant expenditure or remaining funds.",
                                "Payroll and ledger are not added together; duplicate economic events across source systems remain unverified.",
                                "Service dates are compared inclusively; eligibility, extensions and allocations require original terms and independent review.",
                                "No grant compliance clearance, violation or adjustment is established."]}
