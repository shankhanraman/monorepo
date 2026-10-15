import { render, screen } from "@testing-library/react";
import SignInMenu from "./SignInMenu";

afterEach(() => localStorage.clear());

test("guest: offers a field to use an API key", () => {
  render(<SignInMenu />);
  expect(screen.getByText("Use API key")).toBeTruthy();
});

test("with a stored key: shows the prefix and Forget", () => {
  localStorage.setItem("apiKey", "mial_live_demo_do_not_use_in_prod");
  render(<SignInMenu />);
  expect(screen.getByText(/mial_live/)).toBeTruthy();
  expect(screen.getByRole("button", { name: "Forget key" })).toBeTruthy();
});
