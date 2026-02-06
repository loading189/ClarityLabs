import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { AppStateProvider } from "../state/appState";
import AppLayout from "./AppLayout";

function renderLayout(path = "/app/11111111-1111-4111-8111-111111111111/assistant") {
  return render(
    <AppStateProvider>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/app/:businessId" element={<AppLayout />}>
            <Route path="assistant" element={<div>Assistant screen</div>} />
            <Route path="signals" element={<div>Signals center</div>} />
            <Route path="ledger" element={<div>Ledger screen</div>} />
            <Route path="categorize" element={<div>Categorize screen</div>} />
            <Route path="vendors" element={<div>Vendors screen</div>} />
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

    expect(screen.getByText("Assistant screen")).toBeInTheDocument();
    const assistantLink = screen.getByRole("link", { name: "Assistant" });
    expect(assistantLink).toHaveAttribute("aria-current", "page");

    await user.click(screen.getByRole("link", { name: "Signals" }));
    expect(await screen.findByText("Signals center")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Signals" })).toHaveAttribute("aria-current", "page");

    await user.click(screen.getByRole("link", { name: "Ledger" }));
    expect(await screen.findByText("Ledger screen")).toBeInTheDocument();

    await user.click(screen.getByRole("link", { name: "Categorize" }));
    expect(await screen.findByText("Categorize screen")).toBeInTheDocument();

    await user.click(screen.getByRole("link", { name: "Vendors" }));
    expect(await screen.findByText("Vendors screen")).toBeInTheDocument();
  });
});
