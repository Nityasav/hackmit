"""Turn a slice of the City of Boston's Checkbook Explorer into committable records.

    uv run python scripts/fetch_boston_checkbook.py --out /tmp/boston
    uv run python scripts/fetch_boston_checkbook.py --out /tmp/boston --workspace ws_… --commit

Checkbook Explorer publishes every voucher line the City of Boston pays, by
vendor, account and department. It is real money paid to real, named
organizations, released into the public domain under the PDDL, and it is the
only part of this demo that nobody invented.

What the source carries, this maps. What it does not carry, it does not guess.
A spending extract is one side of a ledger, and three things double entry needs
are simply absent from it, so they are *derived* — written under account codes
no Boston account can collide with, carrying a memo that says so, and listed in
the PROVENANCE.md written beside the files:

  * the credit side of each voucher (the City's payable),
  * an opening trial balance,
  * `type` and `report_mapping` for every account.

Nothing else is added. No vendor register, no purchase orders, no receipts: the
source has none of those, so neither does the output, and a three-way match run
against this data will correctly report that the records it needs were never
supplied.

`--payments` writes one more file, and is opt-in because it costs one column the
source does not publish: `payments.method`, written as "unstated". Without it the
accounts-payable control tests have no population and say so; with it they run
against real vouchers. Which of those a demo wants is the demo's call, not this
script's default.

Vendor and department travel in `memo` and `department`, optional columns the
record vocabulary already recognizes, so a duplicate candidate a control test
raises can be read back to the organization it names.

Two same-amount vouchers to one vendor on one day are a *candidate* duplicate
and nothing more. These are real named organizations, and two invoices of equal
value on one day is an ordinary thing that happens.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import httpx

DATASET = "https://data.boston.gov/dataset/checkbook-explorer"
LICENSE = "PDDL (Open Data Commons Public Domain Dedication and Licence)"

#: Only FY24 is listed because only FY24's resource id has been checked against
#: the portal. Another year is `--url`, not a guess made here.
FY24 = ("https://data.boston.gov/dataset/eed1e776-e26e-4123-a3a4-648f286bfa1e/"
        "resource/0b7c9c5f-d1c2-46e7-b738-6ab37a110eef/download/checkbook_explorerfy24.csv")

#: Source columns this reads. Anything else in the file is ignored rather than
#: mapped into a field it does not mean.
SOURCE_COLUMNS = ["Voucher", "Voucher Line", "Distribution Line", "Entered",
                  "Vendor Name", "Account", "Account Descr", "Dept Name", "Monetary Amount"]

#: The derived accounts, as (code, name, type, report_mapping). The codes are
#: deliberately non-numeric: every Boston account code is digits, so none of
#: these can be mistaken for one or collide with one in a later slice.
PAYABLE = ("DERIVED-AP", "Accounts payable (derived contra)", "liability", "balance_sheet")
CASH = ("DERIVED-CASH", "Opening cash (derived)", "asset", "cash")
FUND = ("DERIVED-FUND", "Opening fund balance (derived)", "equity", "equity")

DERIVED_MEMO = "Derived contra line; not present in the Checkbook Explorer extract"


def download(url: str, byte_limit: int) -> str:
    """The published CSV, or its first `byte_limit` bytes.

    The portal honours range requests, so a demo does not have to pull 20 MB to
    look at a week. A ranged read lands mid-line, and that last partial line is
    dropped rather than parsed into a row with a truncated amount.
    """
    headers = {"Range": f"bytes=0-{byte_limit - 1}"} if byte_limit else {}
    with httpx.Client(timeout=180, follow_redirects=True) as client:
        response = client.get(url, headers=headers)
        response.raise_for_status()
        text = response.text
    if byte_limit and response.status_code == 206:
        text = text[: text.rfind("\n") + 1]
    return text


def read(text: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(text, newline=""))
    missing = [c for c in SOURCE_COLUMNS if c not in (reader.fieldnames or [])]
    if missing:
        raise SystemExit("Upstream schema changed; columns absent: " + ", ".join(missing))
    return [row for row in reader if row.get("Voucher")]


def iso(value: str) -> str:
    """`7/5/2023` as `2023-07-05`."""
    return datetime.strptime(value.strip(), "%m/%d/%Y").date().isoformat()


def money(value: str) -> Decimal:
    return Decimal(value.strip().replace(",", "").replace("$", ""))


def amount(value: Decimal) -> str:
    """Exact major units, the way a finance export writes them."""
    return f"{value:.2f}"


class Dropped:
    """Why a voucher did not become a journal, counted rather than swallowed.

    A loader that silently skips rows reports a total that no one can tie back
    to the published file. Every exclusion lands here and is printed and written
    into the provenance note.
    """

    def __init__(self):
        self.reasons: dict[str, int] = defaultdict(int)
        self.examples: dict[str, str] = {}

    def add(self, reason: str, voucher: str) -> None:
        self.reasons[reason] += 1
        self.examples.setdefault(reason, voucher)

    def lines(self) -> list[str]:
        return [f"{count} voucher(s) — {reason} (e.g. {self.examples[reason]})"
                for reason, count in sorted(self.reasons.items())]


def journals(rows: list[dict], start: str, end: str) -> tuple[list[list], Dropped]:
    """Voucher lines as balanced journals, one journal per voucher.

    Grouping is by voucher before anything is filtered, because half a voucher
    is not a smaller journal — it is an unbalanced one. A voucher is taken whole
    or not at all, and the reason it was not taken is recorded.
    """
    by_voucher: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_voucher[row["Voucher"].strip()].append(row)

    out, dropped = [], Dropped()
    for voucher, lines in sorted(by_voucher.items()):
        try:
            dates = {iso(line["Entered"]) for line in lines}
            amounts = [money(line["Monetary Amount"]) for line in lines]
        except (ValueError, ArithmeticError):
            dropped.add("unparseable date or amount", voucher)
            continue
        if len(dates) > 1:
            # Intake requires one accounting date per journal, and picking one
            # of two would date somebody's money to a day it did not move.
            dropped.add("lines entered on different dates", voucher)
            continue
        day = dates.pop()
        if not start <= day <= end:
            continue
        if any(value == 0 for value in amounts):
            dropped.add("a line with a zero amount", voucher)
            continue

        keys = {(line["Voucher Line"].strip(), line["Distribution Line"].strip()) for line in lines}
        if len(keys) != len(lines):
            dropped.add("repeated voucher/distribution line numbers", voucher)
            continue

        entry = []
        for line, value in zip(lines, amounts):
            side = (amount(value), "0.00") if value > 0 else ("0.00", amount(-value))
            entry.append([
                voucher,
                f"{line['Voucher Line'].strip()}-{line['Distribution Line'].strip()}",
                day, line["Account"].strip(), *side,
                line["Vendor Name"].strip(), line["Dept Name"].strip(),
            ])
        net = sum(amounts)
        if net:
            # The City's own payable, which the published extract does not carry.
            # A voucher that already nets to zero needs no contra and gets none.
            side = ("0.00", amount(net)) if net > 0 else (amount(-net), "0.00")
            entry.append([voucher, "contra", day, PAYABLE[0], *side, DERIVED_MEMO, ""])
        out.extend(entry)
    return out, dropped


def chart(rows: list[dict], ledger: list[list], effective_from: str) -> tuple[list[list], list[str]]:
    """One row per account actually used, plus the three derived accounts.

    Type and mapping are derived, not read: Checkbook Explorer is a record of
    spending, so every account in it is an account money was spent on. That is a
    classification this loader makes, and it is named as one in the provenance.
    """
    used = {line[3] for line in ledger}
    names: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        code = row["Account"].strip()
        if code in used:
            names[code].add(row["Account Descr"].strip())

    out, ambiguous = [], []
    for code in sorted(names):
        labels = sorted(names[code])
        if len(labels) > 1:
            # Two descriptions for one code is a real disagreement in the source.
            # The chart may hold each account once, so the first is taken and the
            # alternatives are reported rather than dropped in silence.
            ambiguous.append(f"{code}: {' | '.join(labels)}")
        out.append([code, labels[0], "expense", "operating", effective_from])
    for code, name, kind, mapping in (PAYABLE, CASH, FUND):
        out.append([code, name, kind, mapping, effective_from])
    return out, ambiguous


def opening(ledger: list[list], start: str) -> list[list]:
    """The smallest balanced opening the ledger will accept.

    Intake refuses ledger activity with no opening trial balance, and a trial
    balance cannot be one row. Both figures are the period's own spending, so
    the opening is a restatement of what follows rather than a number chosen to
    look plausible. Both accounts are marked derived in their names.
    """
    total = sum(Decimal(line[4]) for line in ledger)
    return [
        ["DERIVED-OB-1", CASH[0], start, amount(total), "0.00"],
        ["DERIVED-OB-2", FUND[0], start, "0.00", amount(total)],
    ]


#: What `payments.method` says when the source does not say. Checkbook Explorer
#: does not publish whether a voucher was paid by check or by transfer, and
#: "check" written in a column that means it would be a fabrication. This is the
#: column stating that the source is silent, which is a different thing.
UNSTATED = "unstated"


def payments(ledger: list[list]) -> tuple[list[list], Dropped]:
    """Each voucher as one vendor payment. Opt-in, because it costs one column.

    The ledger spine needs nothing invented. This does: `payments` requires a
    `method`, and Checkbook Explorer does not publish one. Everything else is
    published — the voucher number is both the payment id and the City's own
    payment reference, which is what a voucher number is — except `vendor_id`,
    which is an identifier derived from the published name rather than a fact
    about the vendor.

    What it buys is the accounts-payable control tests, which otherwise have no
    population to run against and correctly report that they were given nothing.
    """
    by_voucher: dict[str, list[list]] = defaultdict(list)
    for line in ledger:
        if line[1] != "contra":
            by_voucher[line[0]].append(line)

    out, dropped = [], Dropped()
    for voucher, lines in sorted(by_voucher.items()):
        vendors = {line[6] for line in lines if line[6]}
        if len(vendors) != 1:
            # One payment to two payees is not one payment. Splitting it would
            # invent an allocation the source does not state.
            dropped.add("no single vendor on the voucher", voucher)
            continue
        total = sum(Decimal(line[4]) - Decimal(line[5]) for line in lines)
        if total <= 0:
            # A credit note is not a payment, and intake refuses an amount that
            # is zero or negative rather than storing a reversal as one.
            dropped.add("nets to zero or to a credit", voucher)
            continue
        name = vendors.pop()
        out.append([voucher, vendor_id(name), lines[0][2], UNSTATED, amount(total), voucher, name])
    return out, dropped


def vendor_id(name: str) -> str:
    """A stable id for a published name. An identifier, not a claim about anyone."""
    return "V-" + hashlib.sha256(name.casefold().encode()).hexdigest()[:10]


def duplicate_candidates(ledger: list[list]) -> list[str]:
    """Same vendor, same amount, same day, different vouchers.

    Reported so the demo knows what is in the data before it runs, never as a
    finding. Two invoices of equal value on one day is an ordinary thing.
    """
    seen: dict[tuple, set[str]] = defaultdict(set)
    for entry, line, day, _account, debit, _credit, memo, _dept in ledger:
        if line != "contra" and memo:
            seen[(memo, day, debit)].add(entry)
    return [f"{day} · {memo} · {debit} · vouchers {sorted(v)}"
            for (memo, day, debit), v in sorted(seen.items()) if len(v) > 1]


def write_csv(path: Path, header: list[str], rows: list[list]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


#: The ledger spine, which needs nothing invented. `payments.csv` joins it only
#: when `--payments` is passed, and `push` stages whatever was actually written.
FILES = [
    ("chart-of-accounts.csv", "chart"),
    ("opening-trial-balance.csv", "opening"),
    ("general-ledger.csv", "ledger"),
    ("payments.csv", "payments"),
]


def provenance(url: str, digest: str, start: str, end: str, counts: dict,
               dropped: Dropped, not_paid: Dropped, ambiguous: list[str],
               candidates: list[str], with_payments: bool) -> str:
    return "\n".join([
        "# Provenance",
        "",
        f"Source: City of Boston Checkbook Explorer — {DATASET}",
        f"File: {url}",
        f"Licence: {LICENSE}",
        f"Retrieved: {date.today().isoformat()}",
        f"sha256 of the bytes read: {digest}",
        f"Window: {start} to {end}",
        "",
        "## What is real",
        "",
        "Every voucher number, line number, accounting date, account code, account",
        "description, vendor name, department and amount below is as published. These are",
        "real payments by the City of Boston to real, named organizations.",
        "",
        "## What is derived",
        "",
        "The published extract is the spending side of the City's ledger. Double entry",
        "needs the other side, and these records add it. Each is listed here because none",
        "of it is in the source:",
        "",
        "1. **The credit side of each voucher** — one line per voucher, to the account",
        f"   `{PAYABLE[0]}` ({PAYABLE[1]}), for the voucher's net. Its `memo` reads",
        f"   \"{DERIVED_MEMO}\". A voucher whose lines already net to zero gets no contra line.",
        "2. **The opening trial balance** — two lines, `DERIVED-OB-1` and `DERIVED-OB-2`,",
        f"   against `{CASH[0]}` and `{FUND[0]}`, each for the total spending in the window.",
        "   Intake refuses ledger activity with no opening balance; the source has none.",
        "3. **Account `type` and `report_mapping`** — every Boston account is classified",
        "   `expense`/`operating`, because Checkbook Explorer records spending. The three",
        "   derived accounts carry the types their names state.",
        "",
        *([
            "4. **`payments.method`** — written as `" + UNSTATED + "` on every row, because",
            "   Checkbook Explorer does not publish how a voucher was paid. The column is",
            "   required; the fact is not published; so the column states that. Writing",
            "   \"check\" there would have been a fabrication.",
            "5. **`payments.vendor_id`** — a hash of the published vendor name, so one",
            "   counterparty has one id. It is an identifier, not a claim about anyone.",
            "",
            "Everything else on a payment row is published: the voucher number is both the",
            "payment id and the City's own payment reference, which is what a voucher number",
            "is; the date and the amount are the voucher's own.",
            "",
        ] if with_payments else []),
        "Derived account codes are non-numeric. Every Boston account code is digits, so no",
        "derived account can be confused with, or collide with, a published one.",
        "",
        "## What is absent and stays absent",
        "",
        "The source has no vendor register, purchase orders, goods receipts, invoice",
        "numbers or due dates, so none are written. A three-way match run against these",
        "records will report the records it needs as missing, which is true.",
        *([] if with_payments else [
            "",
            "`payments.csv` was not written either, because it needs a payment method the",
            "source does not publish. Pass `--payments` to write it; the accounts-payable",
            "control tests have no population to run against without it.",
        ]),
        "",
        "## Counts",
        "",
        *[f"- {key}: {value:,}" for key, value in counts.items()],
        "",
        "## Vouchers not loaded",
        "",
        *(["- " + line for line in dropped.lines()] or ["- none"]),
        *([""] + ["- " + line + " (written to the ledger, but not as a payment)"
                  for line in not_paid.lines()] if not_paid.lines() else []),
        "",
        "## Accounts with more than one description in the source",
        "",
        *(["- " + line for line in ambiguous] or ["- none"]),
        "",
        "## Duplicate candidates present in this slice",
        "",
        "Same vendor, same amount, same day, different vouchers. These are *candidates*.",
        "Two invoices of equal value on one day is an ordinary thing, and nothing here is a",
        "finding about a real organization.",
        "",
        *(["- " + line for line in candidates] or ["- none"]),
        "",
    ])


def push(api: str, ws: str, out: Path) -> None:
    """Stage and commit through the ordinary intake, not around it.

    Writing to the database directly would produce records that never met a
    validator, which is the one thing a demo about auditable books must not do.
    """
    # The same header the browser sends: writes into intake data are guarded, and
    # a script is not an exception to that.
    with httpx.Client(base_url=api, timeout=180,
                      headers={"X-SchoolTrace-Reviewer": "local-reviewer"}) as client:
        written = [(name, role) for name, role in FILES if out.joinpath(name).exists()]
        files = [("files", (name, out.joinpath(name).read_bytes(), "text/csv")) for name, _ in written]
        metadata = [{"role": role, "source_system": "boston_checkbook", "amount_unit": "major"}
                    for _, role in written]
        response = client.post(f"/api/workspaces/{ws}/imports", files=files,
                               data={"metadata": json.dumps(metadata)})
        if response.status_code >= 400:
            raise SystemExit(f"Staging failed ({response.status_code}): {response.text}")
        batch = response.json()

        # The validated preview is spread across the batch view, not nested under it.
        print(f"staged {batch['id']}: {batch['counts']}")
        if batch["status"] != "ready_to_commit":
            for item in batch["issues"][:20]:
                print(f"  {item['code']}: {item['message']}")
            raise SystemExit(f"Not committed; the import is {batch['status']}. "
                             f"Open it in the app to resolve the issues above.")

        committed = client.post(
            f"/api/workspaces/{ws}/imports/{batch['id']}/commit",
            json={"expected_version": batch["version"],
                  "idempotency_key": f"boston-{out.name}-{batch['id']}"})
        if committed.status_code >= 400:
            raise SystemExit(f"Commit failed ({committed.status_code}): {committed.text}")
        print(f"committed {batch['id']} into {ws}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default=FY24, help="Checkbook Explorer CSV to read")
    parser.add_argument("--start", default="2023-07-01", help="First accounting date to include")
    parser.add_argument("--end", default="2023-07-31", help="Last accounting date to include")
    parser.add_argument("--bytes", type=int, default=0,
                        help="Read only the first N bytes (0 reads the whole file)")
    parser.add_argument("--out", type=Path, required=True, help="Directory to write the CSVs into")
    parser.add_argument("--payments", action="store_true",
                        help="Also write payments.csv. Turns on the accounts-payable control "
                             "tests, and costs one column the source does not publish: method.")
    parser.add_argument("--api", default="http://127.0.0.1:8000", help="API base URL")
    parser.add_argument("--workspace", default="", help="Workspace to stage the files into")
    parser.add_argument("--commit", action="store_true",
                        help="Stage and commit through the API (requires --workspace)")
    args = parser.parse_args()

    if args.commit and not args.workspace:
        raise SystemExit("--commit needs --workspace; create the workspace in the app first "
                         "so its data origin and period are labelled by the person who owns them.")
    if args.start > args.end:
        raise SystemExit("--start must not be after --end")

    text = download(args.url, args.bytes)
    digest = hashlib.sha256(text.encode()).hexdigest()
    rows = read(text)
    ledger, dropped = journals(rows, args.start, args.end)
    if not ledger:
        covered = sorted({iso(r["Entered"]) for r in rows if r.get("Entered")})
        raise SystemExit(
            f"No vouchers fall in {args.start}..{args.end}. "
            + (f"The bytes read cover {covered[0]}..{covered[-1]}." if covered else "")
            + (" Raise --bytes or drop it to read the whole file." if args.bytes else ""))

    accounts, ambiguous = chart(rows, ledger, args.start)
    balances = opening(ledger, args.start)
    candidates = duplicate_candidates(ledger)

    args.out.mkdir(parents=True, exist_ok=True)
    write_csv(args.out / "chart-of-accounts.csv",
              ["account", "name", "type", "report_mapping", "effective_from"], accounts)
    write_csv(args.out / "opening-trial-balance.csv",
              ["record_id", "account", "balance_date", "debit", "credit"], balances)
    write_csv(args.out / "general-ledger.csv",
              ["entry_id", "line_id", "date", "account", "debit", "credit", "memo", "department"], ledger)

    paid, not_paid = ([], Dropped())
    if args.payments:
        paid, not_paid = payments(ledger)
        write_csv(args.out / "payments.csv",
                  ["payment_id", "vendor_id", "payment_date", "method", "amount", "reference", "memo"], paid)
    else:
        # A stale file from an earlier `--payments` run would be staged by `push`
        # and quietly reintroduce the one invented column this run declined.
        (args.out / "payments.csv").unlink(missing_ok=True)

    derived = sum(1 for line in ledger if line[1] == "contra")
    counts = {
        "source rows read": len(rows),
        "ledger lines written": len(ledger),
        "of which published": len(ledger) - derived,
        "of which derived contra": derived,
        "journals": len({line[0] for line in ledger}),
        "accounts": len(accounts),
        "vendors": len({line[6] for line in ledger if line[1] != "contra"}),
        "departments": len({line[7] for line in ledger if line[7]}),
    }
    if args.payments:
        counts["payments written"] = len(paid)
    (args.out / "PROVENANCE.md").write_text(provenance(
        args.url, digest, args.start, args.end, counts, dropped, not_paid, ambiguous,
        candidates, args.payments))

    for key, value in counts.items():
        print(f"{key}: {value:,}")
    for line in dropped.lines() + [f"{line} (as a payment)" for line in not_paid.lines()]:
        print(f"not loaded: {line}")
    print(f"duplicate candidates: {len(candidates)}")
    print(f"-> {args.out}")

    if args.commit:
        push(args.api, args.workspace, args.out)


if __name__ == "__main__":
    sys.exit(main())
