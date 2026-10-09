import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import UserForm from "./UserForm";

const input = (label: string) => screen.getByLabelText(label) as HTMLInputElement;

test("create mode: submits the data and clears the form", async () => {
  const onSubmit = vi.fn().mockResolvedValue(undefined);
  render(<UserForm submitLabel="Create user" onSubmit={onSubmit} />);

  await userEvent.type(input("Username"), "carol");
  await userEvent.type(input("Email"), "carol@example.com");
  await userEvent.click(screen.getByRole("button", { name: "Create user" }));

  expect(onSubmit).toHaveBeenCalledWith({ username: "carol", email: "carol@example.com" });
  expect(input("Username").value).toBe("");
});

test("edit mode: prefilled, submits changes, keeps values, can cancel", async () => {
  const onSubmit = vi.fn().mockResolvedValue(undefined);
  const onCancel = vi.fn();
  render(
    <UserForm
      initial={{ username: "bob", email: "bob@example.com" }}
      submitLabel="Save"
      onSubmit={onSubmit}
      onCancel={onCancel}
    />,
  );

  expect(input("Username").value).toBe("bob");
  await userEvent.clear(input("Username"));
  await userEvent.type(input("Username"), "robert");
  await userEvent.click(screen.getByRole("button", { name: "Save" }));

  expect(onSubmit).toHaveBeenCalledWith({ username: "robert", email: "bob@example.com" });
  expect(input("Username").value).toBe("robert");
  await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(onCancel).toHaveBeenCalled();
});

test("shows the API error and keeps the input", async () => {
  const onSubmit = vi.fn().mockRejectedValue(new Error("email: value is not a valid email address"));
  render(<UserForm submitLabel="Create user" onSubmit={onSubmit} />);

  await userEvent.type(input("Username"), "carol");
  await userEvent.type(input("Email"), "carol@example.com");
  await userEvent.click(screen.getByRole("button", { name: "Create user" }));

  expect((await screen.findByRole("alert")).textContent).toBe("email: value is not a valid email address");
  expect(input("Username").value).toBe("carol");
});
