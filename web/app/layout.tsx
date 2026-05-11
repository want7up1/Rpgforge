import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { ThemeProvider } from "@/components/ThemeProvider";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"]
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"]
});

export const metadata: Metadata = {
  title: "RPGForge",
  description: "State-driven AI text RPG engine"
};

const themeBootScript = `
(() => {
  try {
    const mode = localStorage.getItem("rpgforge.themeMode") || "day";
    const normalizedMode = mode === "night" || mode === "auto" ? mode : "day";
    const systemPrefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const theme = normalizedMode === "night" || (normalizedMode === "auto" && systemPrefersDark) ? "night" : "day";
    document.documentElement.dataset.themeMode = normalizedMode;
    document.documentElement.dataset.theme = theme;
  } catch {
    document.documentElement.dataset.themeMode = "day";
    document.documentElement.dataset.theme = "day";
  }
})();
`;

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <body className={`${geistSans.variable} ${geistMono.variable}`}>
        <script dangerouslySetInnerHTML={{ __html: themeBootScript }} />
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  );
}
