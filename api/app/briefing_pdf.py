"""Paginated, printable financial review. All text is escaped, never executable HTML."""
from collections import Counter
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether, HRFlowable

from . import db


def render(view):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=(612, 792), leftMargin=48, rightMargin=48,
                            topMargin=54, bottomMargin=48, title=view.get("report_title", "Sherlock financial review"),
                            author="Sherlock")
    styles = getSampleStyleSheet()
    ink = colors.HexColor("#173641")
    styles["Title"].alignment = TA_LEFT
    styles["Title"].fontSize = 28
    styles["Title"].leading = 34
    styles["Title"].textColor = ink
    styles["Heading3"].fontName = "Helvetica-Bold"
    styles["Heading3"].fontSize = 12
    for heading in ("Heading1", "Heading2", "Heading3"):
        styles[heading].keepWithNext = True
        styles[heading].textColor = ink
    styles.add(ParagraphStyle(name="Copy", fontName="Helvetica", fontSize=9, leading=14,
                              spaceAfter=7, alignment=TA_LEFT, textColor=ink, splitLongWords=True))
    styles.add(ParagraphStyle(name="Meta", parent=styles["Copy"], fontSize=8, textColor=colors.HexColor("#55555f")))
    def p(text, style="Copy"):
        text = str(text).replace("\u2011", "-").replace("\u2013", "-").replace("\u2014", "-")
        return Paragraph(escape(text).replace("\n", "<br/>"), styles[style])
    workspace = view["workspace"]
    findings = view["findings"]
    counts = Counter(f["status"] for f in findings if view.get("include_historical_counts") or not f.get("stale"))
    story = [p("S H E R L O C K   /   F I N A N C E", "Meta"), Spacer(1, 12), p(view.get("report_title", "Financial review"), "Title"),
             p(workspace["name"], "Heading2"),
             p(f'{workspace["start"]} to {workspace["end"]} | {workspace.get("currency", "USD")}', "Meta"),
             p(f'Snapshot: {view["snapshot_id"] or "No committed records"}', "Meta"),
             p(f'Generated: {db.now()[:19].replace("T", " ")} UTC', "Meta"), Spacer(1, 8),
             HRFlowable(width="100%", thickness=2, color=ink), Spacer(1, 18)]
    metrics = Table([[p("Needs attention"), p("Evidence gaps"), p("Checks / conclusions passed")],
                     [p(counts["attention"], "Heading1"), p(counts["gap"], "Heading1"), p(counts["pass"], "Heading1")]],
                    colWidths=[172]*3)
    metrics.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),colors.HexColor("#edf4f5")),
                                ("BOX",(0,0),(-1,-1),0.5,colors.HexColor("#d4d4d8")),
                                ("VALIGN",(0,0),(-1,-1),"TOP"),
                                ("LEFTPADDING",(0,0),(-1,-1),12),("TOPPADDING",(0,0),(-1,-1),8)]))
    if view.get("objective"):
        story += [p("Your request", "Heading2"), p(view["objective"]),
                  p("Task recorded: " + view.get("task_created_at", "Not recorded")[:19].replace("T", " ") + " UTC", "Meta")]
    else:
        story += [metrics, Spacer(1,14)]
        keys = [key for key in ("attention", "gap", "pass") if counts[key]]
        if keys:
            tones = {"attention": "#a63c2f", "gap": "#c18a24", "pass": "#278373"}
            strip = Table([[""] * len(keys)], colWidths=[516 * counts[k]/sum(counts.values()) for k in keys], rowHeights=6)
            strip.setStyle(TableStyle([("BACKGROUND",(i,0),(i,0),colors.HexColor(tones[k])) for i,k in enumerate(keys)]))
            story += [strip, Spacer(1,12)]
    if view.get("audit_summary"):
        if view.get("stale"):
            story.append(p("HISTORICAL REPORT - books have changed or the original snapshot is unknown. Counts describe this recorded run only."))
        story += [p("Executive assessment", "Heading2"), p(view["audit_summary"]),
                  p("Run: " + view["thread_id"] + " | Started: " + view["created_at"][:19].replace("T", " ") + " UTC", "Meta")]
        story.append(p("Review coverage", "Heading2"))
        for domain in view["audit_domains"]:
            story += [p(f'{domain["name"]}: {domain["recorded"]}/{domain["total"]} specialists contributed', "Heading3")]
            if domain["not_assessed"]:
                story.append(p("No recorded contribution: " + ", ".join(domain["not_assessed"]), "Meta"))
        if view["audit_gaps"]:
            story.append(p("Unresolved scope and evidence", "Heading2"))
            story += [p(item) for item in view["audit_gaps"]]
    story += [p("Scope and status", "Heading2"),
              p("Automated review of supplied records. Not an independent audit opinion. "
                "An empty result or completed run is not assurance that the books are correct."),
              *([] if view.get("objective") else [p("Agent conclusions remain subject to independent and human review. Historical agent "
                "decisions may predate the current snapshot; verify cited sources before relying on them.")]),
              *([p(f'{view["scan"].get("record_count", 0)} records in the latest deterministic scan.')] if view.get("scan") else [])]
    if not findings:
        story.append(p("No findings have been recorded. Run a review before using this as a decision document."))
    story.append(p("Task result" if view.get("objective") else "Findings and follow-up", "Heading2"))
    for index, finding in enumerate(findings, 1):
        section_start = len(story) - 1 if index == 1 else len(story)
        story += [Spacer(1,8), HRFlowable(width="100%", thickness=.5, color=colors.HexColor("#d9e3e5")),
                  p(f'{index:02d}  /  {finding["title"]}', "Heading3"),
                  p(f'{finding["status"].replace("_"," ").upper()} | {finding["origin"]} | {finding.get("role_label", finding["role"])}', "Meta")]
        if finding.get("stale"):
            story.append(p("HISTORICAL - rerun against the current snapshot."))
        story.append(p(finding["explanation"]))
        if finding.get("rationale"):
            story += [p("Basis for the answer", "Heading3"), p(finding["rationale"])]
        for issue in finding.get("exceptions", []):
            story.append(p(f'{issue["code"].replace("_", " ")}: {issue["detail"]}'))
        if finding.get("amount_cents") is not None:
            story.append(p(f'Check amount: {workspace.get("currency", "USD")} {finding["amount_cents"]/100:,.2f}. Amounts may overlap; not savings.'))
        story += [p("Next step: " + finding["action"]), p(finding.get("review", ""), "Meta"),
                  p("Source evidence: " + ("; ".join(
                      (e.get("source_name") or e.get("source_id") or e.get("role", "Source"))
                      + (f', line {e["line"]}' if e.get("line") else "")
                      + (f' ({e["record_key"]})' if e.get("record_key") else "")
                      for e in finding["evidence"]) or "No source cited / missing input"), "Meta")]
        for question in finding.get("open_questions", []):
            story.append(p("Open question: " + question))
        follow = finding.get("follow_up")
        if follow:
            story.append(p(f'Follow-up: {follow["status"]}; {follow.get("owner") or "Unassigned"}; {follow["note"]}', "Meta"))
        # Keep short findings intact. ReportLab splits oversized groups across pages.
        story[section_start:] = [KeepTogether(story[section_start:])]
    story += [KeepTogether([p("Limitations", "Heading2"), *[p(item) for item in view["limitations"]]])]
    if view["history"]:
        story.append(p("Recorded review history", "Heading2"))
    story += [p(f'{item["created_at"]} | {item.get("summary") or item["kind"]}', "Meta") for item in view["history"]]
    def footer(canvas, document):
        canvas.setStrokeColor(colors.HexColor("#d4d4d8"))
        canvas.line(48, 38, 564, 38)
        canvas.setFont("Helvetica", 8)
        canvas.drawString(48, 26, "SHERLOCK | Supplied-record financial review")
        canvas.drawRightString(564, 26, str(document.page))
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
