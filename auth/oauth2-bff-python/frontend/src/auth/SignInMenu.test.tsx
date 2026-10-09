import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { goTo, session } from "./session";
import SignInMenu from "./SignInMenu";

// No backend in tests: a stand-in session and a mocked navigation.
vi.mock("./session", () => ({
  session: { user: null as { username: string; email: string | null } | null },
  goTo: vi.fn(),
}));

afterEach(() => {
  session.user = null;
  vi.unstubAllGlobals();
});

test("guest: Sign in menu sends Log in / Register to the backend", async () => {
  render(<SignInMenu />);

  await userEvent.click(screen.getByText("Sign in"));
  await userEvent.click(screen.getByRole("button", { name: "Log in" }));
  expect(goTo).toHaveBeenCalledWith("/auth/login");

  await userEvent.click(screen.getByRole("button", { name: "Register" }));
  expect(goTo).toHaveBeenCalledWith("/auth/register");
});

test("signed in: Log out posts to the backend with the CSRF header, then goes home", async () => {
  session.user = { username: "alice", email: "alice@example.com" };
  const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
  vi.stubGlobal("fetch", fetchMock);
  render(<SignInMenu />);

  expect(screen.getByText("alice")).toBeTruthy();
  expect(screen.queryByText("Sign in")).toBeNull();
  await userEvent.click(screen.getByRole("button", { name: "Log out" }));

  expect(fetchMock).toHaveBeenCalledWith("/auth/logout", { method: "POST", headers: { "X-CSRF": "1" } });
  expect(goTo).toHaveBeenCalledWith("/");
});
