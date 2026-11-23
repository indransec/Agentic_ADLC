import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { HOSTILE } from "../test/fixtures";
import { StatusBadge } from "./status-badge";

describe("StatusBadge", () => {
  it("shows a known value in the platform's words, with its colour", () => {
    render(<StatusBadge value="awaiting_sign_off" />);
    const badge = screen.getByText("Awaiting sign-off");
    expect(badge).toHaveClass("badge");
    expect(badge.style.color).not.toBe("");
  });

  it("shows any other value as plain text", () => {
    const { container } = render(<StatusBadge value={HOSTILE[0]} />);
    expect(container.textContent).toBe(HOSTILE[0]);
    expect(container.querySelector(".badge, script, b")).toBeNull();
  });
});
