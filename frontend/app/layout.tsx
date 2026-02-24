import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SolaraDashboard",
  description: "Multi-portal sales & inventory intelligence",
  icons: { icon: "/favicon.ico" },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="bg-zinc-950 text-zinc-50 antialiased">{children}</body>
    </html>
  );
}
