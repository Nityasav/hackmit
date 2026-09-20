import type { Metadata } from "next";
import { JetBrains_Mono, Playfair_Display, Poppins, Raleway } from "next/font/google";
import { DataProvider } from "@/lib/data";
import { AppSidebar } from "@/components/shell/Sidebar";
import { Topbar } from "@/components/shell/Topbar";
import "./globals.css";

// Raleway carries the titles and the interface text.
const raleway = Raleway({ subsets: ["latin"], variable: "--font-raleway" });
// Poppins sets every number, so figures line up column to column.
const poppins = Poppins({ subsets: ["latin"], weight: ["400", "500", "600", "700"], variable: "--font-poppins" });
// Playfair is the small accent: meta lines, notes, the quiet second line.
const playfair = Playfair_Display({ subsets: ["latin"], variable: "--font-playfair" });
// Kept for money, IDs and the decision records, where columns have to line up.
const jetbrains = JetBrains_Mono({ subsets: ["latin"], variable: "--font-jetbrains" });

export const metadata: Metadata = {
  title: "SchoolTrace",
  description: "An Office of the CFO for schools, run by AI agents.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${raleway.variable} ${poppins.variable} ${playfair.variable} ${jetbrains.variable}`}>
      <body className="font-sans text-[14px] leading-snug antialiased">
        <DataProvider>
          <div className="flex h-screen flex-col overflow-hidden md:flex-row">
            <AppSidebar />
            <div className="flex min-w-0 flex-1 flex-col">
              <Topbar />
              <main className="relative flex-1 overflow-auto px-6 py-6">{children}</main>
            </div>
          </div>
        </DataProvider>
      </body>
    </html>
  );
}
