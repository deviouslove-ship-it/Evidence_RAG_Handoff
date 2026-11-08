import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { FactChips } from "./FactChips";

describe("FactChips", () => {
  it("marks edited facts as dirty without triggering a query", () => {
    const onChange = vi.fn();
    render(
      <FactChips
        facts={[{ key: "date", value: "01/01/2026", status: "extracted_unconfirmed" }]}
        onChange={onChange}
      />,
    );
    fireEvent.change(screen.getByLabelText("Sửa date"), { target: { value: "02/01/2026" } });
    expect(onChange).toHaveBeenCalledWith([
      { key: "date", value: "02/01/2026", status: "extracted_unconfirmed", dirty: true },
    ]);
  });

  it("allows the user to confirm an extracted fact", () => {
    const onChange = vi.fn();
    render(
      <FactChips
        facts={[{ key: "date", value: "01/01/2026", status: "extracted_unconfirmed" }]}
        onChange={onChange}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Xác nhận date" }));
    expect(onChange).toHaveBeenCalledWith([
      { key: "date", value: "01/01/2026", status: "user_confirmed", dirty: true },
    ]);
  });
});
