import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { detectSource } from "./source-detection";

describe("source detection", () => {
  const headers = {
    chart: "account,name,type,report_mapping,effective_from",
    opening: "record_id,account,balance_date,debit,credit",
    ledger: "entry_id,line_id,date,account,debit,credit",
    payroll: "record_id,employee_id,service_start,service_end,pay_date,gross,deductions,net,employer_cost,award_id,award_amount",
    grants: "award_id,name,ceiling,valid_from,valid_to",
    budget: "record_id,account,amount,approval_reference",
    invoice: "record_id,vendor_id,invoice_number,service_date,amount",
    fees: "record_id,student_ref,fee_type,charge_date,amount",
    collections: "record_id,collected_by,collection_date,method,amount",
    deposits: "record_id,deposit_date,bank_reference,amount",
    sponsorships: "record_id,sponsor_id,program,pledge_date,due_date,amount",
  };
  for (const [role, header] of Object.entries(headers)) it(`detects ${role} without filename hints`, () => {
    assert.equal(detectSource("unknown.CSV", header + "\r\n").role, role);
  });
  it("maps normalized quoted headers and BOM", () => {
    const result = detectSource("x.csv", '\uFEFF"Record ID","Account","Amount","Approval Reference"\n');
    assert.equal(result.role, "budget");
    assert.equal(result.mapping.approval_reference, "Approval Reference");
  });
  it("does not guess from incomplete or ambiguous schemas", () => {
    assert.equal(detectSource("payroll.csv", "employee_id,amount").role, "document");
    assert.equal(detectSource("x.csv", "record_id,account,amount,approval_reference,vendor_id,invoice_number,service_date").role, "document");
    assert.equal(detectSource("x.csv", headers.budget + ",Account").role, "document");
  });
  it("keeps public files as documents", () => {
    assert.equal(detectSource("x.csv", headers.payroll, true).role, "document");
  });
  it("suggests text roles conservatively", () => {
    assert.equal(detectSource("x.txt", "Award ID: A. Award period: September. Only support is eligible.").role, "policy");
    assert.equal(detectSource("x.md", "Employee: E. 160 hours total; service allocation 60%.").role, "service");
    assert.equal(detectSource("x.txt", "SYN-EMP-01 / SYN-PAY-1: 160 hours total; 96 hours student support.").role, "service");
    assert.equal(detectSource("payroll.txt", "Annual salary expense summary").role, "document");
  });
});
