import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import { DataProvider } from "@/lib/data";
import { AppSidebar } from "@/components/shell/Sidebar";
import { Topbar } from "@/components/shell/Topbar";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const jetbrains = JetBrains_Mono({ subsets: ["latin"], variable: "--font-jetbrains" });

export const metadata: Metadata = {
  title: "SchoolTrace",
  description: "An Office of the CFO for schools, run by AI agents.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${inter.variable} ${jetbrains.variable}`}>
      <body className="font-sans text-[12.5px] leading-snug antialiased">
        <DataProvider>
          <div className="flex h-screen flex-col overflow-hidden md:flex-row">
            <AppSidebar />
            <div className="flex min-w-0 flex-1 flex-col">
              <Topbar />
              <main className="relative flex-1 overflow-auto px-5 py-4">{children}</main>
            </div>
          </div>
        </DataProvider>
      </body>
    </html>
  );
}
