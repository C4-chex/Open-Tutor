import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MarkdownRenderer } from "./markdown-renderer";

vi.mock("mermaid", () => ({
  default: {
    initialize: vi.fn(),
    render: vi.fn().mockResolvedValue({
      svg: '<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"><script>alert(1)</script><text>Safe diagram</text></svg>',
    }),
  },
}));

describe("MarkdownRenderer dependency compatibility", () => {
  it("renders inline and display math through the real KaTeX plugins", () => {
    const { container } = render(
      <MarkdownRenderer content={"Inline $x^2$\n\n$$\n\\frac{1}{2}\n$$"} />,
    );

    expect(container.querySelectorAll(".katex")).toHaveLength(2);
    expect(container.querySelector(".katex-display")).not.toBeNull();
    expect(container.querySelector(".katex-error")).toBeNull();
  });

  it("sanitizes diagram SVG while retaining readable diagram content", async () => {
    const { container } = render(
      <MarkdownRenderer content={"```mermaid\ngraph TD\n A --> B\n```"} />,
    );

    await waitFor(() => expect(screen.getByText("Safe diagram")).toBeInTheDocument());
    expect(container.querySelector("svg")).not.toBeNull();
    expect(container.querySelector("script, [onload]")).toBeNull();
  });

  it("does not enable trusted HTML commands in math", () => {
    const { container } = render(
      <MarkdownRenderer content={"$\\href{javascript:alert(1)}{click}$"} />,
    );

    expect(container.querySelector('a[href^="javascript:"]')).toBeNull();
  });
});
