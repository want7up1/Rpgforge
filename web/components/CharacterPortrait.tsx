"use client";

import Image from "next/image";

import type { CharacterRead } from "@/lib/types";

type CharacterPortraitProps = {
  character: CharacterRead;
  className?: string;
};

export function CharacterPortrait({ character, className = "" }: CharacterPortraitProps) {
  const portraitSource = character.portrait_thumb_url || character.portrait_url;
  const portraitUrl = portraitSource
    ? `${portraitSource}?v=${encodeURIComponent(character.portrait_uploaded_at ?? "")}`
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
      className={`character-portrait-placeholder grid aspect-[3/4] w-full max-w-full self-start place-items-center rounded-md border border-[color:var(--border)] bg-[color:var(--soft-panel)] ${className}`}
    >
      <div className="character-portrait-initials">
        {character.name.slice(0, 2)}
      </div>
    </div>
  );
}
