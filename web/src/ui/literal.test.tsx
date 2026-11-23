// P-13: agent and person text is literal text; markup and script never become elements.
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { HOSTILE } from "../test/fixtures";
import { Literal, MISSING } from "./literal";

describe("Literal", () => {
  it.each(HOSTILE)("shows %s as text", (sample) => {
    const { container } = render(<Literal value={sample} />);
    expect(container.textContent).toBe(sample);
    expect(container.querySelector("script, b, img, a")).toBeNull();
  });

  it("shows nothing as a dash", () => {
    render(
      <>
        <Literal value={null} />
        <Literal value="" />
      </>,
    );
    expect(screen.getAllByText(MISSING)).toHaveLength(2);
  });

  it("shows numbers and structures as text", () => {
    const { container } = render(<Literal value={{ a: "<b>x</b>" }} />);
    expect(container.textContent).toBe('{"a":"<b>x</b>"}');
    expect(container.querySelector("b")).toBeNull();
  });
});
