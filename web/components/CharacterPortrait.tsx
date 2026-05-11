"use client";

import Image from "next/image";

import type { CharacterRead } from "@/lib/types";

type CharacterPortraitProps = {
  character: CharacterRead;
  className?: string;
};

export function CharacterPortrait({ character, className = "" }: CharacterPortraitProps) {
  const portraitUrl = character.portrait_url
    ? `${character.portrait_url}?v=${encodeURIComponent(character.portrait_uploaded_at ?? "")}`
    : null;

  if (portraitUrl) {
    return (
      <Image
        alt={`${character.name} 立绘`}
        className={`aspect-[3/4] w-full max-w-full self-start rounded-md border border-[color:var(--border)] object-cover ${className}`}
        height={640}
        src={portraitUrl}
        unoptimized
        width={480}
      />
    );
  }

  return (
    <div
      className={`grid aspect-[3/4] w-full max-w-full self-start place-items-center rounded-md border border-[color:var(--border)] bg-[color:var(--soft-panel)] ${className}`}
    >
      <div className="grid h-16 w-16 place-items-center rounded-full border border-[color:var(--border)] bg-[color:var(--panel)] text-xl font-semibold text-[color:var(--accent-strong)]">
        {character.name.slice(0, 2)}
      </div>
    </div>
  );
}
