import { describe, expect, it } from "vitest";
import type { ContentNode } from "@/lib/api";
import {
  buildFocusTerms,
  collectContentNodes,
  findFirstContentNode,
  findNodeById,
  findPathToNode,
} from "./content-tree";

const tree: ContentNode[] = [
  {
    id: "chapter-1",
    title: "Chapter 1",
    type: "topic",
    level: 0,
    order_index: 0,
    source_type: "file",
    content: "",
    children: [
      {
        id: "node-a",
        title: "Binary Search",
        type: "section",
        level: 1,
        order_index: 0,
        source_type: "file",
        content: "How binary search works",
        children: [],
      },
      {
        id: "node-b",
        title: "Two Pointers",
        type: "section",
        level: 1,
        order_index: 1,
        source_type: "file",
        content: "",
        children: [
          {
            id: "node-c",
            title: "Sliding Window",
            type: "section",
            level: 2,
            order_index: 0,
            source_type: "file",
            content: "Window technique notes",
            children: [],
          },
        ],
      },
    ],
  },
];

describe("content-tree helpers", () => {
  it("finds the first node with content", () => {
    expect(findFirstContentNode(tree)?.id).toBe("node-a");
  });

  it("finds nodes by id", () => {
    expect(findNodeById(tree, "node-c")?.title).toBe("Sliding Window");
    expect(findNodeById(tree, "missing")).toBeNull();
  });

  it("collects content nodes in traversal order", () => {
    expect(collectContentNodes(tree).map((node) => node.id)).toEqual(["node-a", "node-c"]);
  });

  it("builds the path to a nested node", () => {
    expect(findPathToNode(tree, "node-c").map((node) => node.id)).toEqual([
      "chapter-1",
      "node-b",
      "node-c",
    ]);
  });

  it("builds deduplicated focus terms from titles", () => {
    expect(buildFocusTerms(tree[0].children![1]).slice(0, 4)).toEqual([
      "two",
      "pointers",
      "sliding",
      "window",
    ]);
  });
});
