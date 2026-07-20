import type { Metadata } from "next";
import { Geist_Mono, Press_Start_2P } from "next/font/google";
import { PixelDialogProvider } from "@/components/PixelDialog";
import "./globals.css";

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"]
});

const pressStart2P = Press_Start_2P({
  variable: "--font-press-start",
  weight: "400",
  subsets: ["latin"]
});

export const metadata: Metadata = {
  title: "RPGForge",
  description: "State-driven AI text RPG engine",
  icons: {
    icon: "/rpg-deepseek-logo.png",
    apple: "/rpg-deepseek-logo.png"
  }
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body className={`${geistMono.variable} ${pressStart2P.variable}`}>
        <PixelDialogProvider>{children}</PixelDialogProvider>
      </body>
    </html>
  );
}
