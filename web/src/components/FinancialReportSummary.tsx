"use client";

import styles from "./FinancialReportSummary.module.css";

type FindingStatus = { stale: boolean; status: string };
export function FinancialReportSummary({ findings, company, period, busy, onDownload }: {
  findings: FindingStatus[]; company: string; period: string; busy: boolean; onDownload: () => void;
}) {
  const current = findings.filter(f => !f.stale);
  const groups = [
    { key: "attention", label: "Needs attention", detail: "Review the flagged findings", color: "#b54736" },
    { key: "gap", label: "Evidence gaps", detail: "More supporting records needed", color: "#a87218" },
    { key: "pass", label: "Passed in scope", detail: "Checks and recorded conclusions", color: "#23796c" },
  ].map(group => ({ ...group, count: current.filter(f => f.status === group.key).length }));
  const total = groups.reduce((sum, group) => sum + group.count, 0);
  return <div className={styles.overview}>
    <header className={styles.header}>
      <div><p className={styles.eyebrow}>Sherlock · Financial briefing</p><h2>Financial review report</h2>
        <p className={styles.subtitle}>{company} · {period}</p></div>
      <button onClick={onDownload} disabled={busy} className={styles.download}>
        <svg aria-hidden="true" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M12 3v12m-4-4 4 4 4-4M5 16v5h14v-5" /></svg>
        {busy ? "Preparing PDF…" : "Download PDF"}
      </button>
    </header>
    <div className={styles.cards} aria-label="Finding status breakdown">{groups.map(group => <article key={group.key} className={styles.card} style={{ borderTopColor: group.color }}>
      <div className={styles.label}><span className={styles.dot} style={{ background: group.color }} />{group.label}</div>
      <strong className={styles.count}>{group.count}</strong><p className={styles.detail}>{group.detail}</p>
    </article>)}</div>
    <div className={styles.distribution} aria-hidden="true">{groups.map(group => <span key={group.key} style={{ width: `${total ? group.count / total * 100 : 0}%`, background: group.color }} />)}</div>
    <footer className={styles.footer}><span>{total ? `${total} current results` : "No current results yet"}{findings.length > current.length ? ` · ${findings.length - current.length} historical` : ""}</span><span>Supplied records only · Not an audit opinion</span></footer>
  </div>;
}
