import Link from "next/link";
import type { ReactNode } from "react";

type AppShellProps = {
  children: ReactNode;
  variant?: "default" | "focus" | "gameplay";
};

export function AppShell({ children, variant = "default" }: AppShellProps) {
  const isGameplay = variant === "gameplay";
  const isFocus = variant === "focus" || isGameplay;

  return (
    <main
      className={
        isGameplay
          ? "h-[100dvh] overflow-hidden px-0"
          : isFocus
            ? "min-h-screen px-3 py-3 pb-[calc(1rem+env(safe-area-inset-bottom))] sm:px-8 sm:py-6 lg:px-14"
          : "min-h-screen px-3 py-3 pb-[calc(1rem+env(safe-area-inset-bottom))] sm:px-8 sm:py-6 lg:px-14"
      }
    >
      <section
        className={
          isGameplay
            ? "mx-auto flex h-full w-full flex-col overflow-hidden"
            : isFocus
              ? "mx-auto flex w-full max-w-7xl flex-col gap-4 sm:gap-6"
            : "mx-auto flex w-full max-w-7xl flex-col gap-4 sm:gap-6"
        }
      >
        <header
          className={
            isFocus
              ? "hidden"
              : "flex flex-col gap-3 border-b border-[color:var(--border)] pb-3 sm:gap-4 sm:pb-5 md:flex-row md:items-center md:justify-between"
          }
        >
          <Link href="/" className="flex items-center gap-2 text-lg font-semibold text-[color:var(--foreground)]">
            <span className="brand-mark-small">RF</span>
            <span>RPGForge</span>
          </Link>
          <nav className="site-nav md:justify-end">
            <Link className="app-button" href="/games">
              冒险
            </Link>
            <Link className="app-button app-button-primary" href="/games/new">
              新建冒险
            </Link>
            <Link className="app-button" href="/settings">
              设置
            </Link>
          </nav>
        </header>
        {children}
      </section>
    </main>
  );
}
