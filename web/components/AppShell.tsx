import Link from "next/link";
import type { ReactNode } from "react";

type AppShellProps = {
  children: ReactNode;
  variant?: "default" | "title" | "focus" | "gameplay";
};

export function AppShell({ children, variant = "default" }: AppShellProps) {
  const isGameplay = variant === "gameplay";
  const bare = variant === "title" || variant === "focus" || isGameplay;

  return (
      <main
        className={
          isGameplay
            ? "h-screen h-[100dvh] overflow-hidden px-0"
            : "min-h-screen px-3 py-3 pb-[calc(1rem+env(safe-area-inset-bottom))] sm:px-8 sm:py-6 lg:px-14"
        }
      >
        <section
          className={
            isGameplay
              ? "mx-auto flex h-full w-full flex-col overflow-hidden"
              : "mx-auto flex w-full max-w-7xl flex-col gap-4 sm:gap-6"
          }
        >
          {bare ? null : (
            <header className="px-topbar">
              <Link href="/" className="px-brand px-font text-xs">
                <span aria-hidden="true" className="text-[color:var(--amber)]">▓▓</span>
                RPGFORGE
              </Link>
              <nav aria-label="全站导航" className="px-menu ml-auto">
                <Link className="px-menu-link" href="/games">
                  <span>冒险</span>
                  <span className="px-menu-en">LOAD</span>
                </Link>
                <Link className="px-menu-link" href="/games/new">
                  <span>新建</span>
                  <span className="px-menu-en">NEW</span>
                </Link>
                <Link className="px-menu-link" href="/workshop">
                  <span>工坊</span>
                  <span className="px-menu-en">FORGE</span>
                </Link>
                <Link className="px-menu-link" href="/settings">
                  <span>设置</span>
                  <span className="px-menu-en">SYSTEM</span>
                </Link>
              </nav>
            </header>
          )}
          {children}
        </section>
      </main>
  );
}
