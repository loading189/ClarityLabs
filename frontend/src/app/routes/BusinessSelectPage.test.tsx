import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { AppStateProvider } from "../state/appState";
import BusinessSelectPage from "./BusinessSelectPage";

const fetchDashboard = vi.fn().mockResolvedValue({ cards: [{ business_id: "b1", name: "Biz One" }] });
const createBusiness = vi.fn().mockResolvedValue({ id: "b2", name: "New Biz" });
const deleteBusiness = vi.fn().mockResolvedValue({ deleted: true });
const seedSimV2 = vi.fn().mockResolvedValue({});

vi.mock("../../api/demo", () => ({ fetchDashboard: (...a: unknown[]) => fetchDashboard(...a) }));
vi.mock("../../api/businesses", () => ({
  createBusiness: (...a: unknown[]) => createBusiness(...a),
  deleteBusiness: (...a: unknown[]) => deleteBusiness(...a),
}));
vi.mock("../../api/simV2", () => ({ seedSimV2: (...a: unknown[]) => seedSimV2(...a) }));

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return { ...actual, useNavigate: () => mockNavigate };
});

describe("BusinessSelectPage", () => {
  it("create business flow navigates", async () => {
    render(
      <AppStateProvider>
        <MemoryRouter>
          <BusinessSelectPage />
        </MemoryRouter>
      </AppStateProvider>
    );
    fireEvent.click(screen.getByText("Create business"));
    await waitFor(() => expect(createBusiness).toHaveBeenCalled());
    await waitFor(() => expect(seedSimV2).toHaveBeenCalled());
    expect(mockNavigate).toHaveBeenCalledWith("/app/b2/assistant");
  });

  it("delete business flow calls api and redirects", async () => {
    vi.spyOn(window, "prompt").mockReturnValue("DELETE");
    render(
      <AppStateProvider>
        <MemoryRouter>
          <BusinessSelectPage />
        </MemoryRouter>
      </AppStateProvider>
    );
    fireEvent.click(await screen.findByText("Delete business"));
    await waitFor(() => expect(deleteBusiness).toHaveBeenCalledWith("b1"));
    expect(mockNavigate).toHaveBeenCalledWith("/app/select");
  });
});
