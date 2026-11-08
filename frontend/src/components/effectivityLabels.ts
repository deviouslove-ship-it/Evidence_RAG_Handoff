import type { AmendmentState, VerificationState } from "../types";

/** Axis A: effective status at the requested date. */
export const STATUS_LABELS: Record<AmendmentState, string> = {
  active: "Còn hiệu lực",
  not_yet_effective: "Chưa có hiệu lực",
  modified: "Sửa đổi một phần",
  suspended: "Tạm ngưng",
  repealed: "Hết hiệu lực",
  replaced: "Bị thay thế",
  unknown: "Chưa xác định",
};

/** Axis B: whether a person confirmed it (with source and time). */
export const VERIFICATION_LABELS: Record<VerificationState, string> = {
  verified: "Đã xác minh",
  unverified: "Chưa xác minh",
  not_found: "Không tìm thấy thông tin trong kho",
};
