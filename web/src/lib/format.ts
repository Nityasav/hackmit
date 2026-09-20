/** Sentence-case UI labels for enum values; never use this on submitted values. */
export function displayLabel(value: string): string {
  const text = value.replaceAll("_", " ");
  return (text.charAt(0).toUpperCase() + text.slice(1)).replace(/\b(id|csv|pdf|usd|cad|ap|cfo|ocr)\b/gi, (word) => word.toUpperCase());
}

/** Cents to money, the one format the product renders figures in. */
export function money(cents: number): string {
  const sign = cents < 0 ? "−" : "";
  const abs = Math.abs(cents);
  return `${sign}$${(abs / 100).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}
