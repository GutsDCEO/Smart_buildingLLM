import type { Metadata } from "next";
import "./globals.css";
import { ThemeProvider } from "next-themes";

export const metadata: Metadata = {
  title: "Smart Building AI — Local RAG Assistant",
  description:
    "Privacy-first AI assistant for Smart Building management. Ask questions about HVAC, maintenance, equipment, and facilities — all answered from your local documents.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <ThemeProvider
          attribute="class"
          defaultTheme="dark"
          enableSystem={false}
          storageKey="sb-theme"
        >
          {children}
        </ThemeProvider>
      </body>
    </html>
  );
}
