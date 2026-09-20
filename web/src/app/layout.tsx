import type { Metadata } from "next";
import { JetBrains_Mono, Playfair_Display, Poppins, Raleway } from "next/font/google";
import { DataProvider } from "@/lib/data";
import { ActivityTracker } from "@/components/ActivityTracker";
import { AppSidebar } from "@/components/shell/Sidebar";
import { Topbar } from "@/components/shell/Topbar";
import { createClient } from "@/lib/supabase/server";
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
  title: "Sherlock",
  description: "Sherlock — evidence-led financial investigation for education. Five AI agents, traceable findings, human decisions.",
  applicationName: "Sherlock",
  icons: { icon: [{ url: "/sherlock-mark.svg", type: "image/svg+xml" }] },
};

export default async function RootLayout({ children }: LayoutProps<"/">) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  return (
    <html lang="en" className={`${raleway.variable} ${poppins.variable} ${playfair.variable} ${jetbrains.variable}`}>
      <body className="font-sans text-[14px] leading-snug antialiased">
        {/* Signed out, the only reachable page is the login screen, and it gets
            the window to itself rather than being framed by the dashboard. */}
        {user ? (
          <DataProvider>
            <ActivityTracker />
            <div className="flex h-screen flex-col overflow-hidden md:flex-row">
              <AppSidebar userEmail={user.email ?? ""} />
              <div className="flex min-w-0 flex-1 flex-col">
                <Topbar />
                <main className="relative flex-1 overflow-auto px-6 py-6">{children}</main>
              </div>
            </div>
          </DataProvider>
        ) : (
          children
        )}
      </body>
    </html>
  );
}
