import { QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ProfileGate } from "@/hooks/profile";
import { api } from "@/lib/api";
import { storeProfileId } from "@/lib/profile";
import { queryClient } from "@/lib/queryClient";
import type { PlanPreview, PlanRevision } from "@/lib/types";
import PlanAssistantPage from "@/pages/PlanAssistantPage";

const preview = (name: string, planWeeks = 1): PlanPreview => ({
  ok: true,
  summary: null,
  plan_weeks: planWeeks,
  previous_plan_weeks: 1,
  errors: [],
  warnings: [],
  workouts: [{ name, day: "Monday", previous_day: null, weeks: null, weeks_text: "Every week", status: "added", notes: [], exercises: [] }],
});

describe("Change with AI: applying an answer", () => {
  beforeEach(() => {
    localStorage.clear();
    queryClient.clear();
    storeProfileId(1);
    vi.spyOn(api, "profiles").mockResolvedValue([{ id: 1, name: "Trey", email: null }]);
    vi.spyOn(api, "assistantStatus").mockResolvedValue({ email_enabled: false, email: null });
    vi.spyOn(api, "planRevisions").mockResolvedValue([]);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("ignores a check that finishes after the answer was edited, and applies only checked text", async () => {
    let finishFirst: (p: PlanPreview) => void = () => {};
    const previewPlan = vi
      .spyOn(api, "previewPlan")
      .mockImplementationOnce(() => new Promise((resolve) => (finishFirst = resolve)))
      .mockResolvedValueOnce(preview("Plan B"));
    const applyPlan = vi.spyOn(api, "applyPlan").mockResolvedValue({ id: 1 } as PlanRevision);

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <ProfileGate>
            <PlanAssistantPage />
          </ProfileGate>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    const answer = await screen.findByRole("textbox", { name: /the ai's answer/i });

    fireEvent.change(answer, { target: { value: "plan A" } });
    await userEvent.click(screen.getByRole("button", { name: /check answer/i }));
    fireEvent.change(answer, { target: { value: "plan B" } }); // edited while checking
    finishFirst(preview("Plan A", 3));
    await waitFor(() => expect(screen.getByRole("button", { name: /check answer/i })).toBeEnabled());
    expect(screen.queryByText("Plan A")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /apply to/i })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /check answer/i }));
    await userEvent.click(await screen.findByRole("button", { name: /apply to trey's plan/i }));
    expect(previewPlan).toHaveBeenLastCalledWith("plan B");
    expect(applyPlan).toHaveBeenCalledWith("plan B", false);
  });
});
