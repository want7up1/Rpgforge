import Link from "next/link";
import type { ReactNode } from "react";

import { ThemeToggle } from "@/components/ThemeToggle";

type AppShellProps = {
  children: ReactNode;
  variant?: "default" | "focus";
};

export function AppShell({ children, variant = "default" }: AppShellProps) {
  const isFocus = variant === "focus";

  return (
    <main
      className={
        isFocus
          ? "min-h-screen px-3 py-3 pb-[calc(1rem+env(safe-area-inset-bottom))] sm:px-6 sm:py-4"
          : "min-h-screen px-3 py-3 pb-[calc(1rem+env(safe-area-inset-bottom))] sm:px-8 sm:py-6 lg:px-14"
      }
    >
      <section
        className={
          isFocus
            ? "mx-auto flex w-full max-w-4xl flex-col gap-3 sm:gap-4"
            : "mx-auto flex w-full max-w-7xl flex-col gap-4 sm:gap-6"
        }
      >
        <header
          className={
            isFocus
              ? "flex items-center justify-between border-b border-[color:var(--border)] pb-3"
              : "flex flex-col gap-3 border-b border-[color:var(--border)] pb-3 sm:gap-4 sm:pb-5 md:flex-row md:items-center md:justify-between"
          }
        >
          <Link href="/" className="text-lg font-semibold text-[color:var(--foreground)]">
            RPGForge
          </Link>
          {isFocus ? (
            <ThemeToggle />
          ) : (
            <nav className="app-actions md:justify-end">
              <Link
                className="app-button"
                href="/games"
              >
                游戏列表
              </Link>
              <Link
                className="app-button app-button-primary"
                href="/games/new"
              >
                新建游戏
              </Link>
              <Link
                className="app-button"
                href="/settings"
              >
                设置
              </Link>
              <ThemeToggle />
            </nav>
          )}
        </header>
        {children}
      </section>
    </main>
  );
}
