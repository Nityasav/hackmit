"""Money-in checks: what was charged, what staff recorded as received, what reached the bank.

Kept apart from the ledger checks because this population is traced by reference
strings between four record roles rather than by debit/credit identity. Amounts
come in two kinds and are never mixed or added together: a difference between
two supplied populations (the deposit shortfall against a reference, the excess
deposited over the receipts under a reference, the uncollected remainder of a
fee charge, the unreceived remainder of a pledge) and a gross total of one
population (collections carrying a reference no deposit answers, collections
with no reference at all, receipts banked outside the window, deposits no
receipt accounts for, receipts against an absent charge). Neither kind is a
loss, a recovery, or a figure that may be added to another check's amount.

Refunds, reversals and cancelled obligations have no record role here and are
not modelled: a charge collected and later refunded still reads as collected.
Every explanation that reports a remainder says so.
"""
import unicodedata
from collections import defaultdict
from datetime import date
from hashlib import sha256

# Supplied demo convention for banking receipts, not a statutory deadline.
DEPOSIT_WINDOW_DAYS = 5


def _key(value):
    # One normalisation for every reference join. Staff write these by hand on slips, so case
    # and stray spacing must not split a group or hide a matching deposit. casefold() would go
    # further than that and merge references staff wrote differently: it maps ß to ss, so
    # "Straße-7" and "STRASSE-7" become one group and one reference's shortfall nets off
    # another's surplus. lower() does the case work; NFKC only folds compatibility spellings of
    # the same character, such as the Kelvin sign written for a K.
    return unicodedata.normalize("NFKC", " ".join(value.split())).lower()


def _digest(value):
    return sha256(value.encode()).hexdigest()[:12]


def _total(rows):
    # Clamped here as well as where obligations are credited: a future loader's negative
    # must not turn a gross total into a negative "amount received".
    return sum(max(r["payload"]["amount_cents"], 0) for r in rows)


def _text(row, field):
    return row["payload"].get(field, "").strip()


def _variants(obligations):
    # The join tolerates the case and spacing staff write on a slip; the identity must not.
    # Ingestion commits one record per exact record_id, so FEE-1 and fee-1 are two separate
    # charges. A normalised spelling that several of them share resolves to none of them
    # rather than to whichever sorted first.
    index = defaultdict(list)
    for record_id in obligations:
        index[_key(record_id)].append(record_id)
    return {key: ids[0] for key, ids in index.items() if len(ids) == 1}


def _resolve(raw, obligations, variants):
    return raw if raw in obligations else variants.get(_key(raw))


def _attribute(collections, charged, pledged):
    # A collection answers exactly ONE obligation: the fee charge it names where it names one,
    # the pledge otherwise. Counted under both, a single receipt would close a charge and a
    # pledge at once and report the same money as received twice.
    fee_variants, pledge_variants = _variants(charged), _variants(pledged)
    against, received, unanswered = defaultdict(int), defaultdict(int), []
    for row in collections:
        fee_raw, pledge_raw = _text(row, "fee_record_id"), _text(row, "collection_reference")
        # Resolution, not presence, decides the fallthrough: a dead fee reference must not
        # stop a receipt reaching the pledge it also names.
        if fee_raw and (target := _resolve(fee_raw, charged, fee_variants)) is not None:
            # Intake refuses a non-positive amount today; clamping keeps a future loader's
            # reversal from crediting a negative and inflating a remainder past the charge.
            against[target] += max(row["payload"]["amount_cents"], 0)
        elif pledge_raw and (target := _resolve(pledge_raw, pledged, pledge_variants)) is not None:
            received[target] += max(row["payload"]["amount_cents"], 0)
        elif fee_raw or pledge_raw:
            # Names an obligation this workspace cannot identify. Derived from the same rule
            # that credits, so no receipt can fall between crediting and being reported.
            unanswered.append(row)
    return against, received, unanswered


ATTRIBUTION = ("Each collection record answers one obligation only — the fee charge it names where it names "
               "one, the pledge it names otherwise — so a receipt carrying both references is counted against "
               "the charge and never also against the pledge. It is matched to the obligation whose record_id "
               "it names exactly, or failing that to the single supplied obligation whose record_id differs "
               "from it only in case or spacing; where several differ only that way, a receipt naming none of "
               "them exactly is counted against none and each of them is reported here in full.")

REVERSALS = ("Refunds, reversals and cancelled obligations are not represented in these records and are not "
             "modelled: a charge settled and later refunded still reads here as settled, and a receipt "
             "carrying a negative amount is not treated as reducing what came in.")


def collection_checks(by_role, config, add):
    """Trace fee charges, collections, deposits and pledges through the supplied records only."""
    collections, deposits = by_role["collections"], by_role["deposits"]
    fees, sponsorships = by_role["fees"], by_role["sponsorships"]

    for key, rows, title, explanation, action in [
        ("rc-collections-inventory", collections, "Collection records missing",
         "No collection population supplied, so no receipt can be traced to a bank deposit. Absence of records does not establish that nothing was collected.",
         "Upload the receipt or cash-collection log: record_id, collected_by, collection_date, method, amount."),
        ("rc-deposits-inventory", deposits, "Deposit records missing",
         "No deposit population supplied, so recorded receipts cannot be reconciled to the bank. This does not establish that receipts went undeposited.",
         "Upload the deposit register or bank statement lines: record_id, deposit_date, bank_reference, amount."),
        ("rc-fees-inventory", fees, "Fee charge records missing",
         "No fee charge population supplied, so amounts owed to the school cannot be compared with amounts collected. Missing inputs do not establish that nothing is outstanding.",
         "Upload the fee charge register: record_id, student_ref, fee_type, charge_date, amount."),
        ("rc-sponsorships-inventory", sponsorships, "Sponsorship pledge records missing",
         "No sponsorship pledge population supplied, so pledged support cannot be compared with money received. Missing inputs do not establish that every pledge was received.",
         "Upload the pledge register: record_id, sponsor_id, program, pledge_date, due_date, amount."),
    ]:
        if not rows:
            add(key, title, "rc", "gap", explanation, action=action)

    spelling = {}

    def _mark(raw):
        # Findings quote the reference staff actually wrote; min() keeps the choice
        # independent of the order records arrive in.
        key = _key(raw)
        spelling[key] = min(spelling.get(key, raw), raw)
        return key

    groups, unreferenced = defaultdict(list), []
    for row in collections:
        raw = _text(row, "deposit_reference")
        (groups[_mark(raw)] if raw else unreferenced).append(row)
    banked = defaultdict(list)
    for row in deposits:
        # A deposit answers for exactly one reference: the slip's own where staff wrote
        # one, the bank's otherwise. Reachable under both, one deposit could close two
        # separate groups and report the money as banked twice.
        raw = _text(row, "deposit_reference") or _text(row, "bank_reference")
        banked[_mark(raw) if raw else ""].append(row)
    strays = banked.pop("", [])

    unreconciled = 0
    for reference, rows in sorted(groups.items()):
        matched, display = banked.get(reference, []), spelling[reference]
        collected, deposited = _total(rows), _total(matched)
        digest = _digest(reference)
        if not matched:
            unreconciled += 1
            add("rc-undeposited-" + digest, "Collections with no matching deposit", "rc", "attention",
                f"{len(rows)} collection record(s) carry deposit reference {display}, and no supplied deposit record resolves to that reference. Each deposit is attributed to its own deposit reference where it carries one and to its bank reference otherwise, so a deposit already counted against another reference is not counted again here. The amount is the total recorded as received under this reference, an unreconciled difference against nothing shown reaching the bank. It does not establish theft, loss or misappropriation, and a matching deposit may exist outside the records supplied here.",
                rows, collected,
                "Ask for the deposit slip or the bank statement line for this reference, then reconcile it to the receipts.")
        else:
            if deposited < collected:
                unreconciled += 1
                add("rc-deposit-shortfall-" + digest, "Deposit smaller than the collections against it", "rc", "attention",
                    f"Deposits resolving to reference {display} total less than the collections recorded against it; the amount shown is that shortfall. It does not establish theft, loss or misappropriation: a further deposit, a bank charge, a reversal or a correction may exist outside the supplied records.",
                    rows + matched, collected - deposited,
                    "Ask for the deposit slip and bank statement line for this reference, then reconcile them to each receipt.")
            elif deposited > collected:
                # Reported for the same reason a deposit under an unknown reference is: money
                # reached the bank that no supplied receipt accounts for. Whether it is reported
                # must not turn on which reference string the slip happens to carry.
                unreconciled += 1
                add("rc-deposit-surplus-" + digest, "Deposit larger than the collections against it", "rc", "gap",
                    f"Deposits resolving to reference {display} total more than the collections recorded against it; the amount shown is that excess. Money reached the bank under this reference that no supplied receipt accounts for. This does not establish unrecorded revenue, a diverted receipt or any other irregularity: the receipt may sit in a log that was not uploaded, the deposit may also carry receipts recorded under another reference, or it may cover a period outside this workspace. The amount is an excess over the supplied receipts, not an amount collected, and it may not be added to any other check's amount.",
                    rows + matched, deposited - collected,
                    "Ask which receipts this deposit covers, then record them against this reference or correct the reference on the slip.")
            dates = sorted(date.fromisoformat(r["payload"]["deposit_date"]) for r in matched)
            late, precede = [], []
            for row in rows:
                start = date.fromisoformat(row["payload"]["collection_date"])
                # The earliest deposit that could have carried this receipt. With no deposit
                # dated on or after it the interval is not measurable, and the shortfall check
                # already covers money that never appears.
                after = [d for d in dates if d >= start]
                if not after:
                    # Every supplied deposit under this reference predates the receipt, so none
                    # of them can have carried it. The amounts can still tie, which is exactly
                    # how this reads as reconciled while the money is unaccounted for.
                    precede.append(row)
                if after and (after[0] - start).days > DEPOSIT_WINDOW_DAYS:
                    # A list, not a map on record_key: that key is unique only within a source
                    # system, so two tills filing the same receipt number would collide and the
                    # amount would depend on which row arrived last.
                    late.append((row, (after[0] - start).days))
            if precede:
                unreconciled += 1
                add("rc-deposit-precedes-receipt-" + digest, "Deposits under this reference all predate the receipts", "rc", "attention",
                    f"{len(precede)} of {len(rows)} collection record(s) carrying reference {display} are dated after every supplied deposit that resolves to it, so no supplied deposit can have carried them even though the amounts under this reference tie. The amount is the gross total of those receipts, not an amount at risk. This does not establish theft, loss or misappropriation: the deposit covering them may be dated outside this workspace, may carry another reference, or may not have been supplied.",
                    precede + matched, _total(precede),
                    "Ask for the deposit slip dated on or after these receipts, or correct the dates on the records.")
            if late:
                overdue_rows = [row for row, _ in late]
                worst = max(days for _, days in late)
                add("rc-deposit-timing-" + digest, "Deposit banked outside the supplied window", "rc", "attention",
                    f"{len(late)} of {len(rows)} collection record(s) carrying reference {display} are dated more than {DEPOSIT_WINDOW_DAYS} days before the earliest supplied deposit under that reference dated on or after them; the longest such interval is {worst} calendar days. Each receipt is measured against that deposit rather than against the group's earliest and latest dates, so a reference used over a long period is not flagged for its span alone. The {DEPOSIT_WINDOW_DAYS}-day window is a supplied demo convention, not a statutory or board-approved rule, and a delay does not establish that money was withheld, misused or lost. The amount is the gross total of those receipts, not an amount at risk, and a shared reference does not establish which deposit actually carried which receipt.",
                    overdue_rows + matched, _total(overdue_rows),
                    "Confirm the school's banking-frequency expectation and the reason for the interval before treating this as an exception.")

    for reference, rows in sorted(banked.items()):
        if reference in groups:
            continue
        # Counts against the pass for the same reason a shortfall does: money in the bank that
        # no supplied receipt explains is unreconciled, whichever side of the match it sits on.
        unreconciled += 1
        add("rc-deposit-unmatched-" + _digest(reference), "Deposits no supplied receipt accounts for", "rc", "gap",
            f"{len(rows)} supplied deposit record(s) resolve to reference {spelling[reference]}, which no supplied collection record carries. Money reached the bank against no supplied receipt record. The amount is the gross total of those deposits, one population's total and not a difference between two. This does not establish unrecorded revenue, a diverted receipt or any other irregularity: the receipt may sit in a log that was not uploaded, the reference may be mistyped, or the deposit may cover a population or a period outside this workspace.",
            rows, _total(rows),
            "Supply the receipt log covering this reference, or correct the reference on the deposit slip.")

    if strays:
        unreconciled += 1
        add("rc-deposit-unreferenced", "Deposits with no reference", "rc", "gap",
            f"{len(strays)} supplied deposit record(s) carry neither a deposit reference nor a bank reference, so no receipt can be traced to them and this check cannot tell whether they answer for supplied collections or for money recorded nowhere. The amount is the gross total of those deposits.",
            strays, _total(strays),
            "Record the bank reference on each deposit line, then re-import the deposit register.")

    if unreferenced:
        add("rc-undeposited-unreferenced", "Collections with no deposit reference", "rc", "gap",
            f"{len(unreferenced)} collection record(s) carry no deposit reference, so they cannot be traced to any deposit through the supplied records. An untraceable receipt is a control gap, not a loss: the money may well have been banked, and this check cannot tell either way.",
            unreferenced, _total(unreferenced),
            "Record a deposit reference on each receipt, then supply the deposit slips that cover this period.")

    charged, pledged = defaultdict(list), defaultdict(list)
    for row in fees:
        charged[row["payload"]["record_id"]].append(row)
    for row in sponsorships:
        pledged[row["payload"]["record_id"]].append(row)
    against, received, unanswered = _attribute(collections, charged, pledged)

    # The only affirmative statement this module makes, so it is gated on every population it
    # tracks rather than on the deposit arithmetic alone. Money that ties on one side while
    # sitting unexplained on another is exactly what a green line must never cover.
    if collections and deposits and not unreconciled and not unreferenced and not unanswered:
        add("rc-deposit-reconciliation", "Receipts traced to supplied deposits", "rc", "pass",
            f"Every one of the {len(collections)} supplied collection record(s) carries a deposit reference, and each of the {len(groups)} reference group(s) matched supplied deposit records totalling exactly the amount collected against it, with no supplied deposit left unexplained and every receipt naming an obligation this workspace contains. References are compared with case and repeated spacing ignored, and each supplied deposit is attributed to exactly one reference — its own deposit reference where it carries one, its bank reference otherwise — so no deposit closes more than one group; a deposit that genuinely covers receipts under several references is not recognised as such. {REVERSALS} This compares supplied records with each other only: it does not establish bank statement completeness, or that the funds deposited were the funds collected. Cash that was never written down cannot be detected by any check in this module at all.",
            collections + deposits,
            action="Keep the deposit slips and statement lines for this period alongside the receipt log.")

    outstanding, remainder, untouched = [], 0, 0
    for reference, rows in sorted(charged.items()):
        # Only a positive remainder is reported, so a charge collected in excess can never
        # net off another charge that was not collected.
        short = _total(rows) - against.get(reference, 0)
        if short <= 0:
            continue
        outstanding += rows
        remainder += short
        # against[reference] can exist and be zero once a clamped receipt has touched it, so
        # the split is on the amount credited, never on the key's presence.
        untouched += len(rows) * (against.get(reference, 0) == 0)
    if outstanding:
        add("rc-fees-outstanding", "Fees not fully collected", "rc", "gap",
            f"{len(outstanding)} of {len(fees)} supplied fee charges are not fully covered by supplied collection records: {untouched} are referenced by no collection record at all and {len(outstanding) - untouched} are partly collected. The amount is the remainder — charged less collected — for those charges, counted only where it is positive. {ATTRIBUTION} {REVERSALS} This is money recorded as owed to the school; it is neither a loss nor an error, and this check does not establish which charges remain collectible. A charge may be unpaid, waived, settled outside the supplied records, or receipted under a different reference. The amount sizes a group of {len(outstanding)} separate charges owed by different families, shown here beside one status; it is not a single receivable and is not actionable as one claim.",
            outstanding, remainder,
            "Confirm which charges remain owed, which were waived and which were collected under another reference, then follow the school's collection process.")

    if (fees or sponsorships) and unanswered:
        add("rc-collection-without-charge", "Collections against no supplied obligation", "rc", "gap",
            f"{len(unanswered)} collection record(s) name a fee charge or a pledge that this workspace cannot identify: absent from the supplied registers, or spelled in a way that several supplied records share so that none of them is the one meant. Money was recorded as received against an obligation these records do not contain. The amount is the gross total of those receipts, not a difference between populations. This does not establish an improper receipt: the charge or pledge may sit in a register that was not uploaded, or the reference may be mistyped. The amount sizes a group of {len(unanswered)} separate receipts naming different obligations, shown here beside one status; it is not a single item and is not actionable as one claim.",
            unanswered, _total(unanswered),
            "Supply the register covering these references, or correct the reference on the receipt.")

    period_end = config.get("end")
    if sponsorships and not period_end:
        # The caller supplied no period, and this module says what it did not do rather
        # than returning the silence of a check that never ran.
        add("rc-pledge-ageing-not-run", "Pledge ageing did not run", "rc", "gap",
            f"No workspace period end was supplied to this check, and a pledge cannot be called due without a date to call it due against, so the {len(sponsorships)} supplied pledge(s) were not aged. None of them is reported here as overdue and none as current: the check did not run. This does not establish that every pledge was received, or that any was.",
            sponsorships,
            action="Run this check with the workspace period so pledge due dates can be compared against its end.")

    overdue, unreceived, silent = [], 0, 0
    for reference, rows in sorted(pledged.items()) if period_end else []:
        # A pledge due on the closing day of the period is due inside it.
        if min(r["payload"]["due_date"] for r in rows) > period_end:
            continue
        short = _total(rows) - received.get(reference, 0)
        if short <= 0:
            continue
        overdue += rows
        unreceived += short
        silent += len(rows) * (reference not in received)
    if overdue:
        add("rc-pledge-overdue", "Pledges due without a receipt covering them", "rc", "attention",
            f"{len(overdue)} supplied pledge(s) fell due on or before the workspace period end of {period_end} and are not fully covered by supplied collection records: {silent} are referenced by no collection record at all and {len(overdue) - silent} are partly received. The amount is the remainder — pledged less received — for those pledges, counted only where it is positive. {ATTRIBUTION} {REVERSALS} It does not establish that a sponsor defaulted, withheld payment or breached an agreement; payment may have arrived outside these records or been receipted under another reference. The amount sizes a group of {len(overdue)} separate pledges from different sponsors, shown here beside one status; it is not a single receivable and is not actionable as one claim.",
            overdue, unreceived,
            "Confirm with the sponsor and the bank whether payment arrived, then record the receipt reference against the pledge.")
