"use client";

import type { ReactNode } from "react";

import type { CharacterRead } from "@/lib/types";

type StoryMarkdownProps = {
  className?: string;
  content: string;
  characters?: CharacterRead[];
  onCharacterClick?: (character: CharacterRead) => void;
  showCaret?: boolean;
};

type TextBlock =
  | { type: "heading"; level: number; text: string }
  | { type: "quote"; text: string }
  | { type: "list"; ordered: boolean; items: string[] }
  | { type: "paragraph"; text: string };

type CharacterMatch = {
  label: string;
  character: CharacterRead;
};

export function StoryMarkdown({
  characters = [],
  className = "",
  content,
  onCharacterClick,
  showCaret = false
}: StoryMarkdownProps) {
  const blocks = parseBlocks(content);
  const matchers = buildCharacterMatchers(characters);

  return (
    <div className={`story-markdown ${className}`}>
      {blocks.map((block, index) => renderBlock(block, index, matchers, onCharacterClick))}
      {showCaret ? <span className="story-caret">▋</span> : null}
    </div>
  );
}

function parseBlocks(content: string): TextBlock[] {
  const normalized = content.replace(/\r\n/g, "\n").trim();
  if (!normalized) {
    return [];
  }

  return normalized
    .split(/\n{2,}/)
    .map((chunk) => chunk.trim())
    .filter(Boolean)
    .map(parseBlock);
}

function parseBlock(chunk: string): TextBlock {
  const lines = chunk.split("\n").map((line) => line.trimEnd());
  const heading = lines.length === 1 ? lines[0].match(/^(#{1,4})\s+(.+)$/) : null;
  if (heading) {
    return {
      type: "heading",
      level: Math.min(4, Math.max(3, heading[1].length + 1)),
      text: heading[2].trim()
    };
  }

  if (lines.every((line) => /^>\s?/.test(line.trimStart()))) {
    return {
      type: "quote",
      text: lines.map((line) => line.trimStart().replace(/^>\s?/, "")).join("\n")
    };
  }

  const listItems = lines.map((line) => line.trimStart().match(/^(([-*+])|(\d+[.)]))\s+(.+)$/));
  if (listItems.every(Boolean)) {
    return {
      type: "list",
      ordered: listItems.some((match) => Boolean(match?.[3])),
      items: listItems.map((match) => match?.[4].trim() ?? "")
    };
  }

  return { type: "paragraph", text: lines.join("\n") };
}

function renderBlock(
  block: TextBlock,
  index: number,
  matchers: CharacterMatch[],
  onCharacterClick?: (character: CharacterRead) => void
) {
  if (block.type === "heading") {
    const HeadingTag = block.level === 4 ? "h4" : "h3";
    return (
      <HeadingTag key={index}>
        {renderInline(block.text, matchers, onCharacterClick)}
      </HeadingTag>
    );
  }

  if (block.type === "quote") {
    return (
      <blockquote key={index}>
        <InlineLines
          matchers={matchers}
          onCharacterClick={onCharacterClick}
          text={block.text}
        />
      </blockquote>
    );
  }

  if (block.type === "list") {
    const ListTag = block.ordered ? "ol" : "ul";
    return (
      <ListTag key={index}>
        {block.items.map((item, itemIndex) => (
          <li key={`${index}-${itemIndex}`}>
            {renderInline(item, matchers, onCharacterClick)}
          </li>
        ))}
      </ListTag>
    );
  }

  return (
    <p key={index}>
      <InlineLines
        matchers={matchers}
        onCharacterClick={onCharacterClick}
        text={block.text}
      />
    </p>
  );
}

function InlineLines({
  matchers,
  onCharacterClick,
  text
}: {
  matchers: CharacterMatch[];
  onCharacterClick?: (character: CharacterRead) => void;
  text: string;
}) {
  return text.split("\n").map((line, index, lines) => (
    <FragmentWithBreak key={index} showBreak={index < lines.length - 1}>
      {renderInline(line, matchers, onCharacterClick)}
    </FragmentWithBreak>
  ));
}

function FragmentWithBreak({
  children,
  showBreak
}: {
  children: ReactNode;
  showBreak: boolean;
}) {
  return (
    <>
      {children}
      {showBreak ? <br /> : null}
    </>
  );
}

function renderInline(
  text: string,
  matchers: CharacterMatch[],
  onCharacterClick?: (character: CharacterRead) => void
): ReactNode[] {
  const nodes: ReactNode[] = [];
  const pattern = /(\*\*([^*]+)\*\*|\*([^*]+)\*)/g;
  let cursor = 0;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > cursor) {
      nodes.push(
        ...renderCharacterText(
          text.slice(cursor, match.index),
          match.index,
          matchers,
          onCharacterClick
        )
      );
    }

    if (match[2]) {
      nodes.push(
        <strong key={`${match.index}-strong`}>
          {renderCharacterText(match[2], match.index, matchers, onCharacterClick)}
        </strong>
      );
    } else if (match[3]) {
      nodes.push(
        <em key={`${match.index}-em`}>
          {renderCharacterText(match[3], match.index, matchers, onCharacterClick)}
        </em>
      );
    }

    cursor = match.index + match[0].length;
  }

  if (cursor < text.length) {
    nodes.push(...renderCharacterText(text.slice(cursor), cursor, matchers, onCharacterClick));
  }

  return nodes;
}

function renderCharacterText(
  text: string,
  keyOffset: number,
  matchers: CharacterMatch[],
  onCharacterClick?: (character: CharacterRead) => void
): ReactNode[] {
  if (!onCharacterClick || matchers.length === 0 || !text) {
    return [text];
  }

  const nodes: ReactNode[] = [];
  let cursor = 0;
  while (cursor < text.length) {
    const match = findCharacterMatch(text, cursor, matchers);
    if (!match) {
      const nextIndex = nextPotentialMatchIndex(text, cursor + 1, matchers);
      const end = nextIndex === -1 ? text.length : nextIndex;
      nodes.push(text.slice(cursor, end));
      cursor = end;
      continue;
    }

    nodes.push(
      <button
        className="story-character-link"
        key={`${keyOffset}-${cursor}-${match.character.id}`}
        onClick={() => onCharacterClick(match.character)}
        type="button"
      >
        {text.slice(cursor, cursor + match.label.length)}
      </button>
    );
    cursor += match.label.length;
  }
  return nodes;
}

function buildCharacterMatchers(characters: CharacterRead[]): CharacterMatch[] {
  const matches: CharacterMatch[] = [];
  const seen = new Set<string>();
  for (const character of characters) {
    if (!character.is_visible) {
      continue;
    }
    for (const rawLabel of [character.name, ...character.aliases]) {
      const label = rawLabel.trim();
      if (!label || label.length < 2 || seen.has(label)) {
        continue;
      }
      seen.add(label);
      matches.push({ label, character });
    }
  }
  return matches.sort((a, b) => b.label.length - a.label.length);
}

function findCharacterMatch(
  text: string,
  index: number,
  matchers: CharacterMatch[]
): CharacterMatch | null {
  for (const matcher of matchers) {
    if (!text.startsWith(matcher.label, index)) {
      continue;
    }
    if (!hasAsciiBoundary(text, index, matcher.label.length)) {
      continue;
    }
    return matcher;
  }
  return null;
}

function nextPotentialMatchIndex(
  text: string,
  startIndex: number,
  matchers: CharacterMatch[]
): number {
  let nextIndex = -1;
  for (const matcher of matchers) {
    const found = text.indexOf(matcher.label, startIndex);
    if (found !== -1 && (nextIndex === -1 || found < nextIndex)) {
      nextIndex = found;
    }
  }
  return nextIndex;
}

function hasAsciiBoundary(text: string, index: number, length: number): boolean {
  const before = text[index - 1] ?? "";
  const after = text[index + length] ?? "";
  return !isAsciiWord(before) && !isAsciiWord(after);
}

function isAsciiWord(value: string): boolean {
  return /^[A-Za-z0-9_]$/.test(value);
}
