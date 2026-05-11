"use client";

import { useRouter } from "next/navigation";

type BackButtonProps = {
  fallbackHref: string;
  label?: string;
};

export function BackButton({ fallbackHref, label = "返回上一级" }: BackButtonProps) {
  const router = useRouter();

  function goBack() {
    const referrer = document.referrer ? new URL(document.referrer) : null;
    if (window.history.length > 1 && referrer?.origin === window.location.origin) {
      router.back();
      return;
    }
    router.push(fallbackHref);
  }

  return (
    <button
      className="app-button"
      onClick={goBack}
      type="button"
    >
      {label}
    </button>
  );
}
