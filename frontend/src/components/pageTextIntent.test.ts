import { expect, it } from "vitest";
import { detectPageTextIntent } from "./pageTextIntent";

it.each([
  "Cho tôi nội dung text của trang 17 của văn bản này",
  "Tôi cần text trang 17 của báo cáo này",
  "Đọc lại từ ảnh trang 17 của tài liệu này",
])("uses the selected document for %s", (question) => {
  expect(detectPageTextIntent(question)).toMatchObject({ pageNumber: 17, docHint: "" });
});

it("preserves explicit document identifiers", () => {
  expect(detectPageTextIntent("Đọc nội dung trang 17 Nghị định 351/2026/NĐ-CP"))
    .toMatchObject({ pageNumber: 17, docHint: "Nghị định 351/2026/NĐ-CP" });
});
