/**
 * A fictional vendor invoice as a real PDF, for trying the document lab without
 * a scan of your own.
 *
 * The page carries a text layer, so the server reads it with the PDF's own text
 * rather than falling back to OCR — the same path a digital invoice from a
 * supplier takes. Written by hand because one sample page does not justify a
 * PDF library in the bundle: the format below is the minimum a reader needs,
 * and the cross-reference table is built from measured byte offsets, not
 * guessed ones.
 */

/** Text-showing operators reserve these three characters. */
function escape(text: string): string {
  return text.replace(/([\\()])/g, "\\$1");
}

interface Line {
  text: string;
  /** Points from the top of the page. */
  top: number;
  /** Points from the left edge; the three-column table needs more than one. */
  left?: number;
  size?: number;
  bold?: boolean;
}

function contentStream(lines: Line[]): string {
  const PAGE_HEIGHT = 792;
  const body = lines
    .map(({ text, top, left = 72, size = 11, bold = false }) =>
      ["BT", `/${bold ? "F2" : "F1"} ${size} Tf`, `${left} ${PAGE_HEIGHT - top} Td`, `(${escape(text)}) Tj`, "ET"].join("\n"),
    )
    .join("\n");
  return body + "\n";
}

/** Assemble the objects into a single-page document with a valid xref table. */
function document(lines: Line[]): ArrayBuffer {
  const stream = contentStream(lines);
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> /Contents 4 0 R >>",
    `<< /Length ${stream.length} >>\nstream\n${stream}endstream`,
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
  ];

  let pdf = "%PDF-1.4\n";
  const offsets: number[] = [];
  objects.forEach((object, index) => {
    offsets.push(pdf.length);
    pdf += `${index + 1} 0 obj\n${object}\nendobj\n`;
  });

  const xref = pdf.length;
  pdf += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  // Every offset above is a character count of ASCII-only text, so it is also a
  // byte count. Non-ASCII content would need measuring after encoding.
  for (const offset of offsets) pdf += `${String(offset).padStart(10, "0")} 00000 n \n`;
  pdf += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;

  const bytes = new TextEncoder().encode(pdf);
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer;
}

/**
 * The invoice behind INV-003 in the full-close starter pack, so the document
 * lab and the committed records describe the same fictional purchase.
 */
export function sampleInvoicePdf(serviceDate: string, currency = "USD"): File {
  const lines: Line[] = [
    { text: "NORTHWIND SUPPLY CO.", top: 72, size: 18, bold: true },
    { text: "418 Harbour Road, Riverbend", top: 94, size: 9 },
    { text: "Vendor ID: VEND-NORTHWIND", top: 108, size: 9 },

    { text: "INVOICE", top: 150, size: 14, bold: true },
    { text: "Invoice number: NW-2210", top: 174 },
    { text: `Invoice date: ${serviceDate}`, top: 192 },
    { text: "Purchase order: PO-3318", top: 210 },
    { text: "Goods receipt: not supplied", top: 228 },

    { text: "Bill to: Riverbend Middle School", top: 264 },
    { text: "Attention: Business Office", top: 282 },

    { text: "Description", top: 324, bold: true },
    { text: "Qty", top: 324, left: 380, bold: true },
    { text: "Line total", top: 324, left: 440, bold: true },
    { text: "Science lab consumables, autumn term", top: 348 },
    { text: "40", top: 348, left: 380 },
    { text: `1,850.00 ${currency}`, top: 348, left: 440 },
    { text: "Replacement microscope lamps", top: 366 },
    { text: "12", top: 366, left: 380 },
    { text: `650.00 ${currency}`, top: 366, left: 440 },
    { text: "Delivery and handling", top: 384 },
    { text: "1", top: 384, left: 380 },
    { text: `400.00 ${currency}`, top: 384, left: 440 },

    { text: `Total due: 2,900.00 ${currency}`, top: 426, size: 13, bold: true },
    { text: "Payment terms: net 30 days", top: 450, size: 10 },
    { text: "Remit to: Northwind Supply Co., account 00-4471-9", top: 468, size: 10 },

    { text: "Fictional vendor and fictional purchase, generated as sample data.", top: 720, size: 8 },
  ];
  return new File([document(lines)], "sample-invoice-NW-2210.pdf", { type: "application/pdf" });
}
