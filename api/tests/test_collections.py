"""Deterministic money-in checks: fees charged, cash collected, deposits banked, pledges.

These assert exact cents and the language the findings are allowed to use. An
unreconciled difference is never a theft finding, and no amount here is savings.
"""

import re

import pytest

from app.accounting.review import checks

PERIOD = {"start": "2026-09-01", "end": "2026-09-30"}

# The digests these ids carry are asserted literally in places: a check id is the key saved
# human follow-ups hang off, so moving one must fail here rather than orphan them silently.
BANK_1, BANK_2, GHOST = "5436e7948ad1", "b0330b470446", "ead6ef03d61e"


def collection(key="COL-1", **values):
    return dict(role="collections", record_key=key, source_id="source-collections", locator=2,
                payload=dict(record_id=key, collected_by="Front office", collection_date="2026-09-02",
                             method="cash", amount_cents=50_000, currency="USD") | values)


def deposit(key="DEP-1", **values):
    return dict(role="deposits", record_key=key, source_id="source-deposits", locator=2,
                payload=dict(record_id=key, deposit_date="2026-09-03", bank_reference="BANK-1",
                             amount_cents=50_000, currency="USD") | values)


def fee(key="FEE-1", **values):
    return dict(role="fees", record_key=key, source_id="source-fees", locator=2,
                payload=dict(record_id=key, student_ref="STU-1", fee_type="Field trip",
                             charge_date="2026-09-01", amount_cents=50_000, currency="USD") | values)


def pledge(key="SPO-1", **values):
    return dict(role="sponsorships", record_key=key, source_id="source-sponsors", locator=2,
                payload=dict(record_id=key, sponsor_id="SPON-1", program="Robotics", pledge_date="2026-09-01",
                             due_date="2026-09-10", amount_cents=250_000, currency="USD") | values)


def found(records, config=None):
    return [f for f in checks(records, PERIOD if config is None else config) if f["role"] == "rc"]


def one(records, prefix, config=None):
    # A prefix ending in '-' names a digest family and nothing else: plain startswith let
    # "rc-undeposited-" also pick up rc-undeposited-unreferenced and return whichever the
    # module happened to emit first.
    pattern = re.compile(re.escape(prefix) + ("[0-9a-f]{12}$" if prefix.endswith("-") else "$"))
    matches = [f for f in found(records, config) if pattern.match(f["id"])]
    assert len(matches) == 1, [f["id"] for f in found(records, config)]
    return matches[0]


def test_every_population_absent_is_a_gap_naming_the_upload():
    inventory = {f["id"]: f for f in found([])}
    assert all(f["status"] == "gap" and f["amount_cents"] is None for f in inventory.values())
    assert set(inventory) == {"rc-collections-inventory", "rc-deposits-inventory",
                              "rc-fees-inventory", "rc-sponsorships-inventory"}
    assert "record_id, collected_by, collection_date, method, amount" in inventory["rc-collections-inventory"]["action"]


def test_reconciled_receipts_pass_and_name_what_was_not_tested():
    records = [collection(deposit_reference="BANK-1"), deposit()]
    item = one(records, "rc-deposit-reconciliation")
    assert item["status"] == "pass" and item["amount_cents"] is None
    assert "bank statement completeness" in item["explanation"]
    assert {e["source_id"] for e in item["evidence"]} == {"source-collections", "source-deposits"}
    assert not [f for f in found(records) if f["id"].startswith("rc-undeposited-")]


def test_deposit_reference_matches_either_deposit_or_bank_reference():
    records = [collection(deposit_reference="DEP-SLIP-7"),
               deposit(bank_reference="BANK-9", deposit_reference="DEP-SLIP-7")]
    assert one(records, "rc-deposit-reconciliation")["status"] == "pass"


def test_undeposited_group_reports_the_exact_amount_collected():
    records = [collection("COL-1", deposit_reference="BANK-2", amount_cents=50_000),
               collection("COL-2", deposit_reference="BANK-2", amount_cents=25_050),
               deposit()]
    item = one(records, "rc-undeposited-")
    assert item["status"] == "attention" and item["amount_cents"] == 75_050
    assert "does not establish theft" in item["explanation"]
    assert "may exist outside the records supplied here" in item["explanation"]
    assert "deposit slip" in item["action"]


def test_partial_deposit_reports_only_the_shortfall():
    records = [collection(deposit_reference="BANK-1", amount_cents=50_000),
               deposit(amount_cents=32_500)]
    item = one(records, "rc-deposit-shortfall-")
    assert item["status"] == "attention" and item["amount_cents"] == 17_500
    assert "does not establish theft" in item["explanation"]
    assert not [f for f in found(records) if f["id"] == "rc-deposit-reconciliation"]


def test_the_shortfall_branch_carries_its_own_check_id():
    """Defect F: it reused rc-undeposited-<digest>, so two different checks shared one id."""
    short = [collection(deposit_reference="BANK-1", amount_cents=50_000), deposit(amount_cents=32_500)]
    absent = [collection(deposit_reference="BANK-1", amount_cents=50_000), deposit(bank_reference="GHOST")]
    assert one(short, "rc-deposit-shortfall-")["id"] == "rc-deposit-shortfall-" + BANK_1
    assert one(absent, "rc-undeposited-")["id"] == "rc-undeposited-" + BANK_1
    assert not [f for f in found(short) if f["id"].startswith("rc-undeposited-")]
    assert not [f for f in found(absent) if f["id"].startswith("rc-deposit-shortfall-")]


def test_deposit_larger_than_the_group_is_an_excess_not_a_shortfall():
    """Defect E: an excess under a matched reference was reported nowhere at all."""
    records = [collection(deposit_reference="BANK-1", amount_cents=100), deposit(amount_cents=900_000)]
    item = one(records, "rc-deposit-surplus-")
    assert item["id"] == "rc-deposit-surplus-" + BANK_1
    assert item["status"] == "gap" and item["amount_cents"] == 899_900
    assert "does not establish unrecorded revenue" in item["explanation"]
    # Not a shortfall, and not a clean reconciliation either.
    assert not [f for f in found(records) if f["id"].startswith("rc-deposit-shortfall-")]
    assert not [f for f in found(records) if f["id"] == "rc-deposit-reconciliation"]


def test_the_same_excess_is_reported_whichever_reference_the_slip_carries():
    """Defect E: 'BANK-1' hid the money, 'GHOST' reported it — same records, same 899,900."""
    matched = [collection(deposit_reference="BANK-1", amount_cents=100), deposit(amount_cents=900_000)]
    unmatched = [collection(deposit_reference="BANK-1", amount_cents=100), deposit("DEP-0", amount_cents=100),
                 deposit("DEP-2", bank_reference="GHOST", amount_cents=899_900)]
    assert one(matched, "rc-deposit-surplus-")["amount_cents"] == 899_900
    assert one(unmatched, "rc-deposit-unmatched-")["id"] == "rc-deposit-unmatched-" + GHOST
    assert one(unmatched, "rc-deposit-unmatched-")["amount_cents"] == 899_900


def test_collection_without_a_deposit_reference_is_a_control_gap():
    records = [collection(amount_cents=12_345), deposit()]
    item = one(records, "rc-undeposited-unreferenced")
    assert item["status"] == "gap" and item["amount_cents"] == 12_345
    assert "not a loss" in item["explanation"]
    # An untraceable receipt must not also be reported as a clean reconciliation.
    assert not [f for f in found(records) if f["id"] == "rc-deposit-reconciliation"]


def test_deposit_timing_uses_the_supplied_window_and_says_so():
    records = [collection(collection_date="2026-09-02", deposit_reference="BANK-1"),
               deposit(deposit_date="2026-09-09")]
    item = one(records, "rc-deposit-timing-")
    assert item["status"] == "attention" and item["amount_cents"] == 50_000
    assert "7 calendar days" in item["explanation"] and "not a statutory" in item["explanation"]
    # Banked late is still banked: the amount check still passes.
    assert one(records, "rc-deposit-reconciliation")["status"] == "pass"


def test_deposit_inside_the_window_raises_no_timing_finding():
    records = [collection(collection_date="2026-09-02", deposit_reference="BANK-1"),
               deposit(deposit_date="2026-09-07")]
    assert not [f for f in found(records) if f["id"].startswith("rc-deposit-timing-")]


def test_fee_with_no_collection_is_money_owed_not_a_loss():
    records = [fee("FEE-1", amount_cents=50_000), fee("FEE-2", amount_cents=7_500),
               collection(fee_record_id="FEE-1", deposit_reference="BANK-1"), deposit()]
    item = one(records, "rc-fees-outstanding")
    assert item["status"] == "gap" and item["amount_cents"] == 7_500
    assert "neither a loss nor an error" in item["explanation"]
    assert {e["line"] for e in item["evidence"]} == {2}


def test_fully_collected_fees_raise_no_outstanding_finding():
    records = [fee(), collection(fee_record_id="FEE-1", deposit_reference="BANK-1"), deposit()]
    assert not [f for f in found(records) if f["id"] == "rc-fees-outstanding"]


def test_collection_against_no_supplied_charge():
    records = [fee("FEE-1"), collection(fee_record_id="FEE-404", amount_cents=9_900, deposit_reference="BANK-1"),
               deposit(amount_cents=9_900)]
    item = one(records, "rc-collection-without-charge")
    assert item["status"] == "gap" and item["amount_cents"] == 9_900
    assert "does not establish an improper receipt" in item["explanation"]


def test_pledge_due_before_period_end_without_a_receipt():
    records = [pledge("SPO-1", due_date="2026-09-10", amount_cents=250_000),
               pledge("SPO-2", due_date="2026-09-10", amount_cents=100_000),
               collection(collection_reference="SPO-2", amount_cents=100_000, deposit_reference="BANK-1")]
    item = one(records, "rc-pledge-overdue")
    assert item["status"] == "attention" and item["amount_cents"] == 250_000
    assert "does not establish that a sponsor defaulted" in item["explanation"]


def test_pledge_due_after_the_period_end_is_not_overdue():
    records = [pledge(due_date="2026-10-15")]
    assert not [f for f in found(records) if f["id"].startswith("rc-pledge-overdue")]


def test_checks_are_stable_across_runs_and_record_order():
    """Comparing ids alone let Defect D through: the timing amount depended on row order."""
    records = [collection("COL-1", deposit_reference="BANK-2"), collection("COL-2", deposit_reference="BANK-2"),
               fee("FEE-1"), pledge("SPO-1"), deposit()]
    triples = lambda rows: [(f["id"], f["status"], f["amount_cents"]) for f in found(rows)]
    first = triples(records)
    assert first == triples(list(reversed(records)))
    assert first == triples(records)
    assert len(set(f[0] for f in first)) == len(first)
    assert ("rc-undeposited-" + BANK_2, "attention", 100_000) in first
    assert ("rc-deposit-unmatched-" + BANK_1, "gap", 50_000) in first


def test_every_finding_states_its_limit_and_never_asserts_theft():
    records = [collection("COL-1", deposit_reference="BANK-2"), collection("COL-2"), fee("FEE-2"),
               pledge("SPO-1"), deposit(deposit_date="2026-09-30")]
    # The shortfall and excess branches only fire on their own populations, so lint them too.
    short = [collection("COL-1", deposit_reference="BANK-1", amount_cents=50_000), deposit(amount_cents=1)]
    over = [collection("COL-1", deposit_reference="BANK-1", amount_cents=1), deposit(amount_cents=50_000)]
    items = found(records) + found(short) + found(over) + found([])
    assert {"rc-deposit-shortfall-" + BANK_1, "rc-deposit-surplus-" + BANK_1} <= {f["id"] for f in items}
    assert items and all(f["origin"] == "deterministic" and "not an Auditor verdict" in f["review"] for f in items)
    for f in items:
        text = f["explanation"].lower()
        assert "does not" in text or "cannot" in text, f["id"]
        assert not any(word in text for word in ("stolen", "embezzl", "savings", "recovered")), f["id"]
        if "theft" in text or "misappropriation" in text or "fraud" in text:
            assert "does not establish" in text, f["id"]


def test_one_deposit_cannot_close_two_collection_groups():
    """Defect 1: indexing a deposit under both its references let it satisfy two groups at once."""
    records = [collection("COL-1", deposit_reference="A", amount_cents=50_000),
               collection("COL-2", deposit_reference="B", amount_cents=50_000),
               deposit("DEP-1", deposit_reference="A", bank_reference="B", amount_cents=50_000)]
    items = found(records)
    assert not [f for f in items if f["id"] == "rc-deposit-reconciliation"]
    # The deposit answers for its own deposit reference; group B is left with nothing behind it.
    undeposited = [f for f in items if f["id"].startswith("rc-undeposited-")]
    assert len(undeposited) == 1 and undeposited[0]["amount_cents"] == 50_000
    assert "B" in undeposited[0]["explanation"]


def test_a_blank_deposit_reference_falls_back_to_the_bank_reference():
    records = [collection(deposit_reference="BANK-1"), deposit(deposit_reference="")]
    assert one(records, "rc-deposit-reconciliation")["status"] == "pass"


def test_reference_matching_ignores_case_and_surrounding_whitespace():
    """Defect 2: 'bank-1' and 'BANK-1' were two different references."""
    records = [collection(deposit_reference="bank-1"), deposit(bank_reference=" BANK-1 ")]
    item = one(records, "rc-deposit-reconciliation")
    assert item["status"] == "pass"
    assert not [f for f in found(records) if f["id"].startswith("rc-undeposited-")]
    # The one normalisation every reference join runs through, asserted at its literal digest.
    assert one([collection(deposit_reference=" Bank-1  "), deposit(bank_reference="GHOST")],
               "rc-undeposited-")["id"] == "rc-undeposited-" + BANK_1


def test_matching_folds_a_compatibility_spelling_but_not_a_different_letter():
    """Defect C: casefold() mapped ß to ss, merging two references staff wrote differently."""
    # Kelvin sign written where a K was meant is the same reference; NFKC folds it.
    kelvin = [collection(deposit_reference="BANK"), deposit(bank_reference="bank")]
    assert one(kelvin, "rc-deposit-reconciliation")["status"] == "pass"
    # "Straße-7" and "STRASSE-7" are not, and neither may absorb the other's difference.
    records = [collection("COL-1", deposit_reference="Straße-7", amount_cents=100_000),
               collection("COL-2", deposit_reference="STRASSE-7", amount_cents=100_000),
               deposit("DEP-1", bank_reference="STRASSE-7", amount_cents=200_000)]
    assert not [f for f in found(records) if f["id"] == "rc-deposit-reconciliation"]
    assert one(records, "rc-undeposited-")["amount_cents"] == 100_000
    assert one(records, "rc-deposit-surplus-")["amount_cents"] == 100_000


def test_partly_collected_fee_reports_the_uncollected_remainder():
    """Defect 3: a one-cent receipt used to settle a 5,000.00 charge outright."""
    records = [fee("FEE-1", amount_cents=500_000),
               collection(fee_record_id="FEE-1", amount_cents=100, deposit_reference="BANK-1"),
               deposit(amount_cents=100)]
    item = one(records, "rc-fees-outstanding")
    assert item["status"] == "gap" and item["amount_cents"] == 499_900
    assert "partly collected" in item["explanation"] and "remainder" in item["explanation"]


def test_partly_received_pledge_reports_the_unreceived_remainder():
    """Defect 3: a one-cent receipt referencing the pledge used to close it."""
    records = [pledge("SPO-1", amount_cents=250_000),
               collection(collection_reference="SPO-1", amount_cents=1, deposit_reference="BANK-1"),
               deposit(amount_cents=1)]
    item = one(records, "rc-pledge-overdue")
    assert item["status"] == "attention" and item["amount_cents"] == 249_999
    assert "partly received" in item["explanation"] and "remainder" in item["explanation"]


def test_fee_collected_in_excess_never_offsets_another_charge():
    records = [fee("FEE-1", amount_cents=50_000), fee("FEE-2", amount_cents=7_500),
               collection(fee_record_id="FEE-1", amount_cents=90_000, deposit_reference="BANK-1"),
               deposit(amount_cents=90_000)]
    assert one(records, "rc-fees-outstanding")["amount_cents"] == 7_500


def test_pledge_ageing_without_a_period_end_says_it_did_not_run():
    """Defect 4: the CFO path calls checks(records, {}), which silently disabled the check."""
    records = [pledge("SPO-1", due_date="2026-09-10", amount_cents=250_000)]
    item = one(records, "rc-pledge-ageing-not-run", {})
    assert item["status"] == "gap" and item["amount_cents"] is None
    assert "did not run" in item["explanation"]
    assert not [f for f in found(records, {}) if f["id"].startswith("rc-pledge-overdue")]


def test_pledge_ageing_gap_is_silent_once_a_period_end_is_supplied():
    records = [pledge("SPO-1", due_date="2026-09-10")]
    assert not [f for f in found(records) if f["id"] == "rc-pledge-ageing-not-run"]


def test_pledge_due_on_the_period_end_is_overdue():
    """Defect 4: due_date < period_end let a pledge due on the closing day escape."""
    records = [pledge("SPO-1", due_date="2026-09-30", amount_cents=250_000)]
    assert one(records, "rc-pledge-overdue")["amount_cents"] == 250_000


def test_deposit_no_receipt_accounts_for_is_reported():
    """Defect 5: a deposit under a reference no receipt carries was dropped entirely."""
    records = [collection("COL-1", deposit_reference="BANK-1", amount_cents=50_000),
               deposit("DEP-1", bank_reference="BANK-1", amount_cents=50_000),
               deposit("DEP-2", bank_reference="GHOST", amount_cents=900_000)]
    item = one(records, "rc-deposit-unmatched-")
    assert item["status"] == "gap" and item["amount_cents"] == 900_000
    assert "does not establish unrecorded revenue" in item["explanation"]
    assert {e["source_id"] for e in item["evidence"]} == {"source-deposits"}


def test_deposit_carrying_no_reference_at_all_is_reported():
    records = [collection(deposit_reference="BANK-1"), deposit("DEP-1", bank_reference="BANK-1"),
               deposit("DEP-2", bank_reference="", amount_cents=4_200)]
    item = one(records, "rc-deposit-unreferenced")
    assert item["status"] == "gap" and item["amount_cents"] == 4_200
    assert "cannot" in item["explanation"]


def test_finding_ids_do_not_change_when_a_group_gains_a_row():
    """Defect 6: ids hashed the group's membership, orphaning saved human follow-ups."""
    before = [collection("COL-1", deposit_reference="BANK-2"), fee("FEE-1"),
              pledge("SPO-1", due_date="2026-09-10"), deposit()]
    after = before + [collection("COL-2", deposit_reference="BANK-2"), fee("FEE-2"),
                      pledge("SPO-2", due_date="2026-09-10")]
    assert set(f["id"] for f in found(before)) <= set(f["id"] for f in found(after))
    for prefix in ("rc-undeposited-", "rc-pledge-overdue", "rc-fees-outstanding", "rc-deposit-unmatched-"):
        assert one(before, prefix)["id"] == one(after, prefix)["id"], prefix


def test_collection_without_charge_id_survives_a_second_orphan():
    before = [fee("FEE-1"), collection("COL-1", fee_record_id="FEE-404", deposit_reference="BANK-1"), deposit()]
    after = before + [collection("COL-2", fee_record_id="FEE-405", deposit_reference="BANK-1")]
    assert one(before, "rc-collection-without-charge")["id"] == one(after, "rc-collection-without-charge")["id"]


def test_timing_measures_each_receipt_against_the_deposit_that_banked_it():
    """Defect 7: max(deposit_date) - min(collection_date) flagged a group banked next day throughout."""
    records = [collection("COL-1", collection_date="2026-09-01", deposit_reference="BANK-1", amount_cents=50_000),
               collection("COL-2", collection_date="2026-09-28", deposit_reference="BANK-1", amount_cents=50_000),
               deposit("DEP-1", deposit_date="2026-09-02", amount_cents=50_000),
               deposit("DEP-2", deposit_date="2026-09-29", amount_cents=50_000)]
    assert not [f for f in found(records) if f["id"].startswith("rc-deposit-timing-")]
    assert one(records, "rc-deposit-reconciliation")["status"] == "pass"


def test_timing_reports_only_the_receipts_measured_outside_the_window():
    records = [collection("COL-1", collection_date="2026-09-01", deposit_reference="BANK-1", amount_cents=11_000),
               collection("COL-2", collection_date="2026-09-20", deposit_reference="BANK-1", amount_cents=50_000),
               deposit("DEP-1", deposit_date="2026-09-21", amount_cents=61_000)]
    item = one(records, "rc-deposit-timing-")
    assert item["amount_cents"] == 11_000 and "20 calendar days" in item["explanation"]


def test_aggregated_amounts_say_they_are_not_one_claim():
    records = [fee("FEE-1"), fee("FEE-2"), pledge("SPO-1", due_date="2026-09-10"),
               pledge("SPO-2", due_date="2026-09-10"),
               collection("COL-1", fee_record_id="FEE-404", deposit_reference="BANK-1"),
               collection("COL-2", fee_record_id="FEE-405", deposit_reference="BANK-1"), deposit()]
    for prefix in ("rc-fees-outstanding", "rc-pledge-overdue", "rc-collection-without-charge"):
        text = one(records, prefix)["explanation"]
        assert "separate" in text and "not actionable as one claim" in text, prefix


def test_the_reconciliation_pass_states_its_blind_spots():
    records = [collection(deposit_reference="BANK-1"), deposit()]
    text = one(records, "rc-deposit-reconciliation")["explanation"]
    assert "exactly one reference" in text
    assert "never written down cannot be detected" in text
    assert "bank statement completeness" in text


def test_one_receipt_cannot_close_a_fee_and_a_pledge_at_once():
    """Defect A: fee_record_id and collection_reference were tallied over the same rows."""
    records = [fee("FEE-1", amount_cents=50_000),
               pledge("SPO-1", amount_cents=50_000, due_date="2026-09-10"),
               collection("COL-1", amount_cents=50_000, fee_record_id="FEE-1",
                          collection_reference="SPO-1", deposit_reference="BANK-1"),
               deposit("DEP-1", amount_cents=50_000)]
    # The receipt answers the charge it names, so the pledge is still unreceived in full.
    assert not [f for f in found(records) if f["id"] == "rc-fees-outstanding"]
    item = one(records, "rc-pledge-overdue")
    assert item["status"] == "attention" and item["amount_cents"] == 50_000
    assert "answers one obligation only" in item["explanation"]


def test_a_receipt_naming_no_charge_still_answers_the_pledge_it_names():
    records = [pledge("SPO-1", amount_cents=50_000, due_date="2026-09-10"),
               collection("COL-1", amount_cents=50_000, collection_reference="SPO-1", deposit_reference="BANK-1"),
               deposit("DEP-1", amount_cents=50_000)]
    assert not [f for f in found(records) if f["id"] == "rc-pledge-overdue"]


def test_charges_differing_only_in_case_are_not_merged():
    """Defect B: _key casefolded the identity, so FEE-1's overpayment netted off fee-1."""
    records = [fee("FEE-1", amount_cents=50_000), fee("fee-1", amount_cents=50_000),
               collection("COL-1", amount_cents=80_000, fee_record_id="FEE-1", deposit_reference="BANK-1"),
               deposit("DEP-1", amount_cents=80_000)]
    item = one(records, "rc-fees-outstanding")
    assert item["amount_cents"] == 50_000
    assert "1 of 2 supplied fee charges" in item["explanation"]
    assert "1 are referenced by no collection record at all" in item["explanation"]


def test_pledges_differing_only_in_case_are_not_merged():
    records = [pledge("SPO-1", amount_cents=100_000, due_date="2026-09-10"),
               pledge("spo-1", amount_cents=100_000, due_date="2026-09-10"),
               collection("COL-1", amount_cents=150_000, collection_reference="SPO-1", deposit_reference="BANK-1"),
               deposit("DEP-1", amount_cents=150_000)]
    assert one(records, "rc-pledge-overdue")["amount_cents"] == 100_000


def test_a_receipt_still_reaches_a_charge_written_in_another_case():
    records = [fee("FEE-1", amount_cents=50_000),
               collection("COL-1", amount_cents=50_000, fee_record_id=" fee-1 ", deposit_reference="BANK-1"),
               deposit("DEP-1", amount_cents=50_000)]
    assert not [f for f in found(records) if f["id"] == "rc-fees-outstanding"]
    assert not [f for f in found(records) if f["id"] == "rc-collection-without-charge"]


def test_timing_counts_every_collection_sharing_a_record_key():
    """Defect D: keying `late` on record_key dropped one of two tills filing the same number."""
    second = collection("COL-1", amount_cents=20_000, collection_date="2026-09-01", deposit_reference="BANK-1")
    second["source_id"] = "source-collections-b"
    records = [collection("COL-1", amount_cents=10_000, collection_date="2026-09-01", deposit_reference="BANK-1"),
               second, deposit("DEP-1", deposit_date="2026-09-20", amount_cents=30_000)]
    item = one(records, "rc-deposit-timing-")
    assert item["id"] == "rc-deposit-timing-" + BANK_1
    assert item["amount_cents"] == 30_000
    assert "2 of 2 collection record(s)" in item["explanation"]
    assert one(list(reversed(records)), "rc-deposit-timing-")["amount_cents"] == 30_000


def test_a_negative_receipt_cannot_inflate_a_remainder_past_the_charge():
    """Defect G: a reversal arriving as a negative amount reported 60,000 owed on a 50,000 charge."""
    records = [fee("FEE-1", amount_cents=50_000),
               collection("COL-1", fee_record_id="FEE-1", amount_cents=-10_000, deposit_reference="BANK-1"),
               deposit("DEP-1", amount_cents=-10_000)]
    assert one(records, "rc-fees-outstanding")["amount_cents"] == 50_000
    pledges = [pledge("SPO-1", amount_cents=50_000, due_date="2026-09-10"),
               collection("COL-1", collection_reference="SPO-1", amount_cents=-10_000, deposit_reference="BANK-1"),
               deposit("DEP-1", amount_cents=-10_000)]
    assert one(pledges, "rc-pledge-overdue")["amount_cents"] == 50_000


def test_the_remainder_checks_disclose_that_reversals_are_out_of_scope():
    records = [fee("FEE-2", amount_cents=7_500), pledge("SPO-2", due_date="2026-09-10"),
               collection("COL-1", deposit_reference="BANK-1"), deposit()]
    for check in ("rc-fees-outstanding", "rc-pledge-overdue", "rc-deposit-reconciliation"):
        assert "Refunds, reversals" in one(records, check)["explanation"], check


def test_one_helper_does_not_confuse_two_checks_sharing_a_prefix():
    records = [collection("COL-1", deposit_reference="BANK-2"), collection("COL-2"), deposit()]
    assert one(records, "rc-undeposited-")["id"] == "rc-undeposited-" + BANK_2
    assert one(records, "rc-undeposited-unreferenced")["id"] == "rc-undeposited-unreferenced"
    # With no group of the digest family present, the helper must refuse rather than hand back
    # the unreferenced check under the same prefix.
    with pytest.raises(AssertionError):
        one([collection("COL-1"), deposit()], "rc-undeposited-")


# Round four. Every case below produced an affirmative "reconciled" pass, or silence, over money
# the module could not account for. They are the reason the pass is gated on every population
# rather than on the deposit arithmetic alone.

def test_a_receipt_naming_an_ambiguous_charge_is_reported_not_swallowed():
    # FEE-1 and fee-1 are two committed charges, so "Fee-1" identifies neither. The receipt used
    # to credit nothing and appear in no finding, while the deposit leg tied and reported a pass.
    records = [fee("FEE-1"), fee("fee-1"),
               collection("COL-1", fee_record_id="FEE-1", deposit_reference="BANK-1"),
               collection("COL-2", fee_record_id="fee-1", deposit_reference="BANK-1"),
               collection("COL-3", fee_record_id="Fee-1", amount_cents=777_000, deposit_reference="BANK-1"),
               deposit("DEP-1", amount_cents=877_000)]
    assert one(records, "rc-collection-without-charge")["amount_cents"] == 777_000
    assert not [f for f in found(records) if f["status"] == "pass"]


def test_a_receipt_naming_an_absent_pledge_is_reported():
    # Only fee_record_id was ever checked for orphans, so a receipt naming a pledge this
    # workspace does not contain went unreported entirely.
    records = [pledge("SPO-1", amount_cents=100_000),
               collection("COL-1", collection_reference="SPO-1", amount_cents=100_000, deposit_reference="BANK-1"),
               collection("COL-2", collection_reference="SPO-999", amount_cents=500_000, deposit_reference="BANK-1"),
               deposit("DEP-1", amount_cents=600_000)]
    assert one(records, "rc-collection-without-charge")["amount_cents"] == 500_000
    assert not [f for f in found(records) if f["status"] == "pass"]


def test_a_dead_fee_reference_does_not_block_the_pledge_it_also_names():
    # The fallthrough is on resolution, not on presence: naming a fee that does not exist must
    # not strand the receipt, nor let the same money answer a charge and a pledge at once.
    records = [fee("FEE-1", amount_cents=10_000), pledge("SPO-1", amount_cents=250_000),
               collection("COL-1", amount_cents=250_000, fee_record_id="FEE-404",
                          collection_reference="SPO-1", deposit_reference="BANK-1"),
               deposit("DEP-1", amount_cents=250_000)]
    ids = [f["id"] for f in found(records)]
    assert not [i for i in ids if i.startswith("rc-pledge-overdue")]
    assert sum(1 for f in found(records) if f["amount_cents"] == 250_000) == 0


def test_deposits_dated_before_the_receipt_cannot_have_banked_it():
    # The amounts tie, so every arithmetic check was satisfied while cash taken on the 28th was
    # reported as reaching the bank on the 3rd.
    records = [collection("COL-1", collection_date="2026-09-28", deposit_reference="BANK-1"),
               deposit("DEP-1", deposit_date="2026-09-03")]
    precedes = one(records, "rc-deposit-precedes-receipt-")
    assert precedes["status"] == "attention" and precedes["amount_cents"] == 50_000
    assert not [f for f in found(records) if f["status"] == "pass"]


def test_unexplained_bank_money_suppresses_the_pass():
    records = [collection("COL-1", deposit_reference="BANK-1"), deposit("DEP-1"),
               deposit("DEP-2", bank_reference="GHOST", amount_cents=900_000)]
    assert one(records, "rc-deposit-unmatched-")["amount_cents"] == 900_000
    assert not [f for f in found(records) if f["status"] == "pass"]


def test_a_deposit_with_no_reference_suppresses_the_pass():
    records = [collection("COL-1", deposit_reference="BANK-1"), deposit("DEP-1"),
               deposit("DEP-2", bank_reference="", deposit_reference="", amount_cents=900_000)]
    assert one(records, "rc-deposit-unreferenced")["amount_cents"] == 900_000
    assert not [f for f in found(records) if f["status"] == "pass"]


def test_the_pass_still_fires_when_everything_genuinely_reconciles():
    # The gate has to stay useful: suppressing the pass unconditionally would be honest and
    # worthless, so a clean set must still say so.
    records = [fee("FEE-1"), collection("COL-1", fee_record_id="FEE-1", deposit_reference="BANK-1"), deposit("DEP-1")]
    assert one(records, "rc-deposit-reconciliation")["status"] == "pass"


def test_a_gross_total_is_never_negative():
    # Intake refuses a negative today; the clamp is what keeps a future loader from printing a
    # negative "amount received" if it ever stops refusing.
    records = [fee("FEE-1"), collection("COL-1", fee_record_id="FEE-404", amount_cents=-5_000),
               deposit("DEP-1")]
    assert all((f["amount_cents"] or 0) >= 0 for f in found(records))
