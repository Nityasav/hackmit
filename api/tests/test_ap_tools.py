from app.agents import ap_tools


def test_get_vendor_returns_known_vendor():
    vendor = ap_tools.get_vendor("V-08")
    assert vendor is not None
    assert vendor.name == "Campus Supply Co."


def test_get_vendor_missing_returns_none():
    assert ap_tools.get_vendor("V-does-not-exist") is None


def test_list_invoices_filters_by_vendor_and_status():
    matched = ap_tools.list_invoices(vendor_id="V-08", status="matched")
    assert {inv.id for inv in matched} == {"INV-2291", "INV-2291A", "INV-3102", "INV-3102B"}


def test_get_purchase_order_returns_requested_line_only():
    lines = ap_tools.get_purchase_order("PO-901", line=1)
    assert len(lines) == 1
    assert lines[0].line == 1


def test_get_receipts_for_po_matches_invoice_receipt_ids():
    invoice = ap_tools.get_invoice("INV-2291")
    receipts = ap_tools.get_receipts_for_po(invoice.po_id, invoice.po_line)
    assert [r.id for r in receipts] == invoice.receipt_ids


def test_find_duplicate_candidates_flags_same_vendor_same_amount():
    """V-08 has four $2,400.00 invoices; the naive vendor+amount scan flags all of them
    as candidates. Separate goods receipts are what actually clears each pair (F-08)."""
    candidates = ap_tools.find_duplicate_candidates("INV-2291")
    assert {inv.id for inv in candidates} == {"INV-2291A", "INV-3102", "INV-3102B"}


def test_duplicate_candidates_have_separate_receipts_as_counterevidence():
    """INV-2291 / 2291A look like duplicates but each has its own receipt batch (F-08)."""
    invoice = ap_tools.get_invoice("INV-2291")
    duplicate = ap_tools.find_duplicate_candidates("INV-2291")[0]
    receipts_a = ap_tools.get_receipts_for_po(invoice.po_id, invoice.po_line)
    receipts_b = ap_tools.get_receipts_for_po(duplicate.po_id, duplicate.po_line)
    assert receipts_a[0].batch != receipts_b[0].batch


def test_get_invoice_packet_bundles_everything():
    packet = ap_tools.get_invoice_packet("INV-2302")
    assert packet["invoice"].id == "INV-2302"
    assert packet["vendor"].id == "V-12"
    assert packet["vendor"].bank_changed_at == "2026-09-27"
    assert packet["purchase_order"].id == "PO-930"


def test_get_invoice_packet_missing_invoice_returns_none():
    assert ap_tools.get_invoice_packet("INV-nope") is None


def test_payment_batch_holds_bank_change_vendor():
    batch = ap_tools.get_payment_batch("PAY-B9")
    assert "INV-2302" in batch.held_invoice_ids
    assert "INV-2302" in batch.hold_reasons
