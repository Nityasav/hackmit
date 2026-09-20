import type { FormatFileProps } from "@/components/ui/file-card-collections";

/**
 * Which card face a stored file gets, from its extension.
 *
 * The intake accepts PDFs, the record importer accepts CSVs, and a handful of
 * documents arrive as plain text or Markdown — but a file is named by whoever
 * uploaded it, so anything can turn up. An unrecognised extension falls back to
 * the "txt" face, which is the neutral one: lines of prose and no claim about
 * the contents. Never guess a richer face than the extension supports, or the
 * card says "spreadsheet" over a file nothing can read as one.
 */
const BY_EXTENSION: Record<string, FormatFileProps> = {
  pdf: "pdf",
  doc: "doc",
  docx: "doc",
  rtf: "doc",
  md: "md",
  mdx: "mdx",
  txt: "txt",
  log: "txt",
  csv: "csv",
  tsv: "csv",
  xls: "xls",
  xlsx: "xlsx",
  ppt: "ppt",
  pptx: "pptx",
  zip: "zip",
  rar: "rar",
  tar: "tar",
  gz: "gz",
  html: "html",
  htm: "html",
  js: "js",
  mjs: "js",
  jsx: "jsx",
  ts: "code",
  tsx: "tsx",
  css: "css",
  json: "json",
  py: "code",
  sql: "code",
  png: "png",
  jpg: "jpg",
  jpeg: "jpeg",
  gif: "img",
  webp: "img",
  svg: "img",
  heic: "img",
  mp4: "video",
  mov: "video",
  webm: "video",
};

/**
 * `name` is a filename ("waiver.pdf"), a bare suffix (".pdf") or either with the
 * case the filesystem happened to use.
 */
export function fileFormat(name: string): FormatFileProps {
  const extension = name.toLowerCase().split(".").pop() ?? "";
  return BY_EXTENSION[extension] ?? "txt";
}
