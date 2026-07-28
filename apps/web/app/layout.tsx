import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Loomi-Brain",
  description:
    "Secure single-owner second brain for cited retrieval and controlled agents.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
