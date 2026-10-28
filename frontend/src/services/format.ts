const inr = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 });
const num = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 });
const ist = new Intl.DateTimeFormat("en-IN", {
  timeZone: "Asia/Kolkata",
  dateStyle: "medium",
  timeStyle: "short",
});

export const money = (v: number | null | undefined) => (v == null ? "—" : inr.format(v));
export const number = (v: number | null | undefined) => (v == null ? "—" : num.format(v));
export const pct = (v: number | null | undefined) => (v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(2)}%`);
const istDate = new Intl.DateTimeFormat("en-IN", { timeZone: "Asia/Kolkata", dateStyle: "medium" });
const istHm = new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit" });

/** Daily bars are stamped at IST midnight; show those as a session date rather than "12:00 am". */
export const istTime = (iso: string | null | undefined) => {
  if (!iso) return "unknown";
  const d = new Date(iso);
  return istHm.format(d) === "00:00" ? `${istDate.format(d)} (daily bar)` : `${ist.format(d)} IST`;
};
