import mailbox
from email.message import EmailMessage
from pathlib import Path

import pytest

from app.agents import ar_tools


def _write_pdf(path: Path, lines: list[str]) -> None:
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path))
    y = 750
    for line in lines:
        c.drawString(50, y, line)
        y -= 20
    c.showPage()
    c.save()


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "invoices").mkdir()
    (tmp_path / "bank_exports").mkdir()
    (tmp_path / "crm").mkdir()
    (tmp_path / "operations").mkdir()
    (tmp_path / "notes").mkdir()
    (tmp_path / "email_archive").mkdir()

    _write_pdf(
        tmp_path / "invoices" / "INV-TEST-1_C001.pdf",
        ["Invoice INV-TEST-1", "Customer: Acme Co", "Customer ID: C001", "Total $1234.56"],
    )
    _write_pdf(tmp_path / "invoices" / "INV-TEST-2_C002.pdf", ["Page 1 real content"])

    (tmp_path / "bank_exports" / "deposits.csv").write_text(
        "date,amount,reference\n2025-01-01,500.00,DEP-1\n", encoding="utf-8"
    )
    (tmp_path / "crm" / "customer_master.csv").write_text(
        "customer_id,name,alias\nC001,Acme Co,Acme\n", encoding="utf-8"
    )
    (tmp_path / "operations" / "ar_aging_snapshot.csv").write_text(
        "customer_id,days_overdue\nC001,10\n", encoding="utf-8"
    )
    (tmp_path / "notes" / "controller_close_notes.txt").write_text("Nothing unusual this quarter.", encoding="utf-8")

    eml = EmailMessage()
    eml["Subject"] = "Invoice question"
    eml["From"] = "customer@example.com"
    eml["Date"] = "Mon, 01 Jan 2025 00:00:00 +0000"
    eml.set_content("We received an invoice for $999.99, please confirm.")
    (tmp_path / "email_archive" / "msg1.eml").write_bytes(bytes(eml))

    mbox_path = tmp_path / "email_archive" / "support_inbox.mbox"
    box = mailbox.mbox(str(mbox_path))
    box.lock()
    mbox_msg = EmailMessage()
    mbox_msg["Subject"] = "Support ticket"
    mbox_msg["From"] = "support@example.com"
    mbox_msg["Date"] = "Tue, 02 Jan 2025 00:00:00 +0000"
    mbox_msg.set_content("Ticket body text.")
    box.add(mbox_msg)  # mailbox.mbox.add() wraps a plain Message into mboxMessage internally
    box.flush()
    box.unlock()

    return tmp_path


def test_list_invoice_files(workspace: Path):
    result = ar_tools.list_invoice_files(str(workspace))
    assert result["files"] == ["INV-TEST-1_C001.pdf", "INV-TEST-2_C002.pdf"]


def test_read_invoices_extracts_page_1_text(workspace: Path):
    result = ar_tools.read_invoices(["INV-TEST-1_C001.pdf"], str(workspace))
    doc = result["documents"]["INV-TEST-1_C001.pdf"]
    assert "Total $1234.56" in doc["page_1_text"]
    assert "C001" in doc["page_1_text"]
    assert doc["page_count"] == 1


def test_read_invoices_reports_missing_file(workspace: Path):
    result = ar_tools.read_invoices(["does_not_exist.pdf"], str(workspace))
    assert result["documents"]["does_not_exist.pdf"]["error"] == "not found"


def test_read_invoices_rejects_oversized_batch(workspace: Path):
    result = ar_tools.read_invoices([f"f{i}.pdf" for i in range(ar_tools.MAX_INVOICE_BATCH + 1)], str(workspace))
    assert "error" in result


def test_read_invoices_blocks_path_traversal(workspace: Path):
    result = ar_tools.read_invoices(["../../etc/passwd"], str(workspace))
    assert "outside the authorized workspace" in result["documents"]["../../etc/passwd"]["error"]


def test_read_bank_exports(workspace: Path):
    result = ar_tools.read_bank_exports(str(workspace))
    rows = result["files"]["deposits.csv"]
    assert rows == [{"date": "2025-01-01", "amount": "500.00", "reference": "DEP-1"}]


def test_read_crm_master(workspace: Path):
    result = ar_tools.read_crm_master(str(workspace))
    assert result["files"]["customer_master.csv"][0]["alias"] == "Acme"


def test_read_operations_files_reads_csv_and_text(workspace: Path):
    result = ar_tools.read_operations_files(str(workspace))
    assert result["operations/ar_aging_snapshot.csv"][0]["days_overdue"] == "10"
    assert "Nothing unusual" in result["notes/controller_close_notes.txt"]


def test_read_email_archive_reads_eml_and_mbox(workspace: Path):
    result = ar_tools.read_email_archive(str(workspace))
    subjects = {m["subject"] for m in result["messages"]}
    assert "Invoice question" in subjects
    assert "Support ticket" in subjects
    eml_message = next(m for m in result["messages"] if m["subject"] == "Invoice question")
    assert "999.99" in eml_message["body"]


def test_tool_specs_match_registry():
    assert {spec["name"] for spec in ar_tools.AR_READ_TOOL_SPECS} == set(ar_tools.AR_READ_TOOLS)


def test_no_ar_tool_exposes_workspace_as_a_model_choice():
    for spec in ar_tools.AR_READ_TOOL_SPECS:
        assert "workspace" not in spec["parameters"].get("properties", {})
