import { act, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { listStudyGoals, type StudyGoal } from "@/lib/api";
import { TimelineView } from "./timeline-view";

vi.mock("@/lib/api", () => ({ listStudyGoals: vi.fn() }));

function deferredGoals() {
  let resolve!: (goals: StudyGoal[]) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<StudyGoal[]>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function goal(title: string): StudyGoal {
  return {
    id: title, title, user_id: "user", course_id: null, objective: title,
    success_metric: null, current_milestone: null, next_action: null,
    status: "active", confidence: null, target_date: null, metadata_json: null,
    linked_task_count: 0, created_at: null, updated_at: null, completed_at: null,
  };
}

describe("TimelineView", () => {
  beforeEach(() => vi.mocked(listStudyGoals).mockReset());

  it("keeps the current course's goals when an older request finishes last", async () => {
    const old = deferredGoals();
    const current = deferredGoals();
    vi.mocked(listStudyGoals).mockReturnValueOnce(old.promise).mockReturnValueOnce(current.promise);
    const { rerender } = render(<TimelineView courseId="old" />);
    rerender(<TimelineView courseId="current" />);

    await act(async () => current.resolve([goal("Current goal")]));
    await act(async () => old.resolve([goal("Old goal")]));

    expect(screen.getByText("Current goal")).toBeInTheDocument();
    expect(screen.queryByText("Old goal")).not.toBeInTheDocument();
  });

  it("keeps loading the current course if an old request fails", async () => {
    const old = deferredGoals();
    const current = deferredGoals();
    vi.mocked(listStudyGoals).mockReturnValueOnce(old.promise).mockReturnValueOnce(current.promise);
    const { rerender } = render(<TimelineView courseId="old" />);
    rerender(<TimelineView courseId="current" />);

    await act(async () => old.reject(new Error("Old request failed")));
    expect(screen.getByText("加载中…")).toBeInTheDocument();

    await act(async () => current.resolve([goal("Current goal")]));
    expect(screen.getByText("Current goal")).toBeInTheDocument();
  });

  it("does not show the previous course's goals when the new request fails", async () => {
    vi.mocked(listStudyGoals).mockResolvedValueOnce([goal("Old goal")]);
    const current = deferredGoals();
    vi.mocked(listStudyGoals).mockReturnValueOnce(current.promise);
    const { rerender } = render(<TimelineView courseId="old" />);
    expect(await screen.findByText("Old goal")).toBeInTheDocument();

    rerender(<TimelineView courseId="current" />);
    expect(screen.queryByText("Old goal")).not.toBeInTheDocument();
    await act(async () => current.reject(new Error("Request failed")));

    expect(screen.queryByText("Old goal")).not.toBeInTheDocument();
    expect(screen.queryByText("加载中…")).not.toBeInTheDocument();
  });
});
