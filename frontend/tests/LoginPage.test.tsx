import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as authApi from "../src/api/auth";
import { ApiError } from "../src/api/client";
import { AuthProvider } from "../src/context/AuthContext";
import { LoginPage } from "../src/pages/LoginPage";

vi.mock("../src/api/auth");

function renderLoginPage() {
  return render(
    <MemoryRouter initialEntries={["/login"]}>
      <AuthProvider>
        <LoginPage />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe("LoginPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    sessionStorage.clear();
  });

  it("disables submit until both fields are filled", async () => {
    const user = userEvent.setup();
    renderLoginPage();

    const submit = screen.getByTestId("login-submit");
    expect(submit).toBeDisabled();

    await user.type(screen.getByTestId("login-username"), "account_owner");
    expect(submit).toBeDisabled();

    await user.type(screen.getByTestId("login-password"), "correct horse battery staple");
    expect(submit).toBeEnabled();
  });

  it("shows a generic error on invalid credentials, without revealing which field was wrong", async () => {
    const user = userEvent.setup();
    vi.spyOn(authApi, "login").mockRejectedValue(
      new ApiError(401, { error: "unauthorized", message: "Invalid username or password" }),
    );
    renderLoginPage();

    await user.type(screen.getByTestId("login-username"), "account_owner");
    await user.type(screen.getByTestId("login-password"), "wrong-password");
    await user.click(screen.getByTestId("login-submit"));

    await waitFor(() => {
      expect(screen.getByTestId("login-error")).toHaveTextContent("Invalid username or password");
    });
  });

  it("stores the token in sessionStorage on successful login", async () => {
    const user = userEvent.setup();
    vi.spyOn(authApi, "login").mockResolvedValue({ token: "abc123", expiresAt: new Date().toISOString() });
    renderLoginPage();

    await user.type(screen.getByTestId("login-username"), "account_owner");
    await user.type(screen.getByTestId("login-password"), "correct horse battery staple");
    await user.click(screen.getByTestId("login-submit"));

    await waitFor(() => {
      expect(sessionStorage.getItem("transactagent_token")).toBe("abc123");
    });
  });
});
