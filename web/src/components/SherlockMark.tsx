import Image from "next/image";

/** Shared vector mark: crisp at favicon, sidebar and login sizes. */
export function SherlockMark({ size = 36 }: { size?: number }) {
  return <Image src="/sherlock-mark.svg" width={size} height={size} alt="" aria-hidden="true" className="shrink-0" />;
}
