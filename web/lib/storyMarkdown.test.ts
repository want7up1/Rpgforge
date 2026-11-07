import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import { StoryMarkdown } from "@/components/StoryMarkdown";
const html = (content: string) => renderToStaticMarkup(createElement(StoryMarkdown, { content }));
it("保留现有标题、强调、引用与列表的受控语法", () => {
  const result = html("### 站台\n\n**钥匙**与*雨声*。\n\n> 有人来了\n\n- 门口\n- 车厢");
  expect(result).toContain("<h3>站台</h3>"); expect(result).toContain("<strong>钥匙</strong>"); expect(result).toContain("<blockquote>"); expect(result).toContain("<ul>");
});
it("流式未闭合强调的尾部文字不丢失", () => { expect(html("她拿着**尚未写完")).toContain("尚未写完"); });
it("代码块内标题保持普通文本，HTML按文本转义", () => {
  const result = html("```\n### 代码里的标题\n```\n\n<script>example()</script>");
  expect(result).not.toContain("<h3>"); expect(result).toContain("&lt;script&gt;");
});
