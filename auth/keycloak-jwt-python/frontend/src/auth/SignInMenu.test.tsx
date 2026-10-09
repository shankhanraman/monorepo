import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { keycloak } from "./keycloak";
import SignInMenu from "./SignInMenu";

// Never contact Keycloak in tests: a stand-in with the fields SignInMenu reads.
vi.mock("./keycloak", () => ({
  keycloak: {
    authenticated: false,
    tokenParsed: undefined as { preferred_username?: string } | undefined,
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
  },
}));

afterEach(() => {
  keycloak.authenticated = false;
  keycloak.tokenParsed = undefined;
});

test("guest: Sign in menu offers Log in and Register", async () => {
  render(<SignInMenu />);

  await userEvent.click(screen.getByText("Sign in"));
  await userEvent.click(screen.getByRole("button", { name: "Log in" }));
  expect(keycloak.login).toHaveBeenCalled();

  await userEvent.click(screen.getByRole("button", { name: "Register" }));
  expect(keycloak.register).toHaveBeenCalled();
});

test("signed in: shows the username and Log out", async () => {
  keycloak.authenticated = true;
  keycloak.tokenParsed = { preferred_username: "alice" };
  render(<SignInMenu />);

  expect(screen.getByText("alice")).toBeTruthy();
  expect(screen.queryByText("Sign in")).toBeNull();
  await userEvent.click(screen.getByRole("button", { name: "Log out" }));
  expect(keycloak.logout).toHaveBeenCalled();
});
