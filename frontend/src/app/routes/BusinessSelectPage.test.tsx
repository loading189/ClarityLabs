import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { AppStateProvider } from "../state/appState";
import BusinessSelectPage from "./BusinessSelectPage";

const createBusiness = vi.fn();
const deleteBusiness = vi.fn();
const joinBusiness = vi.fn();
const reload = vi.fn();

let businesses: Array<{ business_id: string; business_name: string; role: string }> = [];
let config = { pilot_mode_enabled: false, allow_business_delete: false };

vi.mock("../../api/businesses", () => ({
  createBusiness: (...a: unknown[]) => createBusiness(...a),
  deleteBusiness: (...a: unknown[]) => deleteBusiness(...a),
  joinBusiness: (...a: unknown[]) => joinBusiness(...a),
}));

vi.mock("../../api/config", () => ({
  fetchConfig: () => Promise.resolve(config),
}));

vi.mock("../../hooks/useBusinessesMine", () => ({
  useBusinessesMine: () => ({
    businesses,
    loading: false,
    error: null,
    reload,
  }),
}));

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return { ...actual, useNavigate: () => mockNavigate };
});

describe("BusinessSelectPage", () => {
  beforeEach(() => {
    businesses = [];
    config = { pilot_mode_enabled: false, allow_business_delete: false };
    createBusiness.mockResolvedValue({
      business: { id: "b2", name: "New Biz", org_id: "org-1", created_at: "now" },
      membership: { business_id: "b2", business_name: "New Biz", role: "owner" },
    });
    deleteBusiness.mockResolvedValue({ deleted: true });
    reload.mockResolvedValue(undefined);
    mockNavigate.mockReset();
  });

  it("renders empty state and creates a business", async () => {
    render(
      <AppStateProvider>
        <MemoryRouter>
          <BusinessSelectPage />
        </MemoryRouter>
      </AppStateProvider>
    );

    expect(screen.getByText(/No businesses yet/i)).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText("Business name"), {
      target: { value: "New Biz" },
    });
    fireEvent.click(screen.getByText("Create business"));

    await waitFor(() => expect(createBusiness).toHaveBeenCalledWith({ name: "New Biz" }));
    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith("/app/b2/summary"));
  });

  it("allows delete when flag enabled and user is owner", async () => {
    businesses = [{ business_id: "b1", business_name: "Biz One", role: "owner" }];
    config = { pilot_mode_enabled: false, allow_business_delete: true };

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
    await waitFor(() => expect(reload).toHaveBeenCalled());
  });
});
