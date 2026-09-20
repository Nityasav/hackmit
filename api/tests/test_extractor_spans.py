"""Citations are computed from the page text, not taken from the model.

`extractor_server.py` used to ask the model for "exact zero-based Unicode
source spans". Measured against NuExtract3 on a real two-page document that
produced zero usable fields in 117 seconds, while locating the same values in
code produced seven exact spans in 21. `validate()` compares
`page_text[start:end]` to the value, so a miscounted offset does not degrade a
citation — it fails the entire response.
"""

from app.extractor_server import build_template, locate, observation

PAGES = [
    {"page": 1, "text": "Employee ID EMP-016\n"
                        "Pay Period 2023-12-22 to 2024-01-04\n"
                        "Service Period 2023-12-22 to 2024-01-04\n"
                        "Gross  Pay $3538.46 USD"},
    {"page": 2, "text": "Title I 60% SVC-REC-EMP-016-1 IDEA Part B 40%"},
]


def _slice(page: int, start: int, end: int) -> str:
    return next(p["text"] for p in PAGES if p["page"] == page)[start:end]


def test_a_located_span_is_exactly_the_value():
    page, start, end = locate("EMP-016", PAGES, "employee_id")
    assert _slice(page, start, end) == "EMP-016"


def test_a_repeated_value_is_disambiguated_by_its_field_name():
    """The same date prints under both "Pay Period" and "Service Period".
    Abstaining lost correct extractions; picking blindly cites the wrong row."""
    _, start, _ = locate("2023-12-22", PAGES, "service_start")
    assert PAGES[0]["text"][max(0, start - 30):start].strip().endswith("Service Period")


def test_a_value_inside_a_longer_string_prefers_the_standalone_one():
    """EMP-016 also occurs inside SVC-REC-EMP-016-1 on page 2."""
    page, start, end = locate("EMP-016", PAGES, "employee_id")
    assert page == 1 and _slice(page, start, end) == "EMP-016"


def test_a_value_wrapped_differently_still_resolves():
    """The model may echo one space where the page prints two."""
    page, start, end = locate("Gross Pay", PAGES, "description")
    assert _slice(page, start, end) == "Gross  Pay"


def test_a_value_absent_from_the_page_is_never_returned():
    """The safety property: a value with no locatable source is fabricated
    evidence, and a blank is recoverable by a human where that is not."""
    result = observation("invoice_number", "INV-DOES-NOT-EXIST", PAGES)
    assert result["status"] == "unreadable"
    assert result["value"] is None and result["start"] is None


def test_an_absent_field_is_a_stated_abstention():
    assert observation("po_id", None, PAGES) == {
        "status": "missing", "value": None, "page": None, "start": None, "end": None,
    }


def test_the_template_asks_only_for_verbatim_strings():
    """A typed slot invites the model to reformat, and a reformatted value
    cannot be found on the page, so it would arrive as an abstention."""
    assert set(build_template(["a", "b"]).values()) == {"verbatim-string"}
