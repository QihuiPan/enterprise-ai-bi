export const money = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

export const number = new Intl.NumberFormat("en-US");

export function compactCurrency(value) {
  return `$${Math.round(value / 1000)}k`;
}
