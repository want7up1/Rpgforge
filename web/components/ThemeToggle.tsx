"use client";

import { useThemeMode } from "@/components/ThemeProvider";

const themeLabels = {
  day: "白天",
  night: "夜间",
  auto: "自动"
};

export function ThemeToggle() {
  const { mode, cycleMode } = useThemeMode();

  return (
    <button
      aria-label={`当前主题：${themeLabels[mode]}，点击切换`}
      className="app-button"
      onClick={cycleMode}
      suppressHydrationWarning
      title={`主题：${themeLabels[mode]}`}
      type="button"
    >
      主题：{themeLabels[mode]}
    </button>
  );
}
