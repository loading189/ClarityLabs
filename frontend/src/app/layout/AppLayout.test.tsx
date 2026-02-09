import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { AppStateProvider } from "../state/appState";
import AppLayout from "./AppLayout";

vi.mock("../auth/AuthContext", () => ({
  useAuth: () => ({
    user: { id: "user-1", name: "Test User", email: "test@example.com" },
    logout: vi.fn(),
  }),
}));

vi.mock("../../hooks/useBusinessesMine", () => ({
  useBusinessesMine: () => ({
    businesses: [{ business_id: "11111111-1111-4111-8111-111111111111", business_name: "Acme", role: "advisor" }],
    loading: false,
    error: null,
    reload: vi.fn(),
  }),
}));

function renderLayout(path = "/app/11111111-1111-4111-8111-111111111111/advisor") {
  return render(
    <AppStateProvider>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/app/:businessId" element={<AppLayout />}>
            <Route path="advisor" element={<div>Inbox screen</div>} />
            <Route path="signals" element={<div>Signals center</div>} />
            <Route path="ledger" element={<div>Ledger screen</div>} />
            <Route path="summary" element={<div>Summary screen</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </AppStateProvider>
  );
}

describe("AppLayout sidebar navigation", () => {
  it("navigates to each sidebar route", async () => {
    const user = userEvent.setup();
    renderLayout();

    expect(screen.getByText("Inbox screen")).toBeInTheDocument();
    const inboxLink = screen.getByRole("link", { name: "Inbox" });
    expect(inboxLink).toHaveAttribute("aria-current", "page");

    await user.click(screen.getByRole("link", { name: "Signals" }));
    expect(await screen.findByText("Signals center")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Signals" })).toHaveAttribute("aria-current", "page");

    await user.click(screen.getByRole("link", { name: "Ledger" }));
    expect(await screen.findByText("Ledger screen")).toBeInTheDocument();

    await user.click(screen.getByRole("link", { name: "Summary" }));
    expect(await screen.findByText("Summary screen")).toBeInTheDocument();
  });
});
