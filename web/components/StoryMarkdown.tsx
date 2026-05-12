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
  | { type: "plain"; text: string }
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
  if (isFencedCodeBlock(lines)) {
    return {
      type: "plain",
      text: lines
        .filter((line) => !line.trimStart().startsWith("```"))
        .join("\n")
        .trim()
    };
  }

  if (isMarkdownTable(lines)) {
    return { type: "plain", text: lines.join("\n") };
  }

  const heading = lines.length === 1 ? lines[0].match(/^(#{3,4})\s+(.+)$/) : null;
  if (heading) {
    return {
      type: "heading",
      level: heading[1].length,
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

function isFencedCodeBlock(lines: string[]): boolean {
  if (lines.length < 2) {
    return false;
  }
  return (
    lines[0].trimStart().startsWith("```") &&
    lines[lines.length - 1].trimStart().startsWith("```")
  );
}

function isMarkdownTable(lines: string[]): boolean {
  if (lines.length < 2) {
    return false;
  }
  const hasPipeRows = lines.every((line) => line.includes("|"));
  const tableDividerPattern = /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/;
  const hasDivider = lines.some((line) => tableDividerPattern.test(line));
  return hasPipeRows && hasDivider;
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

  if (block.type === "plain") {
    return (
      <p className="story-plain-text" key={index}>
        <PlainLines text={block.text} />
      </p>
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

function PlainLines({ text }: { text: string }) {
  return text.split("\n").map((line, index, lines) => (
    <FragmentWithBreak key={index} showBreak={index < lines.length - 1}>
      {line}
    </FragmentWithBreak>
  ));
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
  const pattern = /(`([^`]+)`|\*\*([^*]+)\*\*|\*([^*]+)\*)/g;
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
        <code className="story-inline-code" key={`${match.index}-code`}>
          {match[2]}
        </code>
      );
    } else if (match[3]) {
      nodes.push(
        <strong key={`${match.index}-strong`}>
          {renderCharacterText(match[3], match.index, matchers, onCharacterClick)}
        </strong>
      );
    } else if (match[4]) {
      nodes.push(
        <em key={`${match.index}-em`}>
          {renderCharacterText(match[4], match.index, matchers, onCharacterClick)}
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
