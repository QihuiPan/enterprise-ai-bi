export const number = new Intl.NumberFormat("en-US");

export const SUPPORTED_CURRENCIES = Object.freeze([
  { code: "USD", label: "USD — US dollar" },
  { code: "GBP", label: "GBP — British pound" },
]);

const currencyFormatters = new Map();
const compactCurrencyFormatters = new Map();

function supportedCurrency(currency) {
  return SUPPORTED_CURRENCIES.some(({ code }) => code === currency) ? currency : "USD";
}

export function formatCurrency(value, currency = "USD") {
  const code = supportedCurrency(currency);
  if (!currencyFormatters.has(code)) {
    currencyFormatters.set(code, new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: code,
      maximumFractionDigits: 0,
    }));
  }
  return currencyFormatters.get(code).format(Number(value) || 0);
}

export function formatCompactCurrency(value, currency = "USD") {
  const code = supportedCurrency(currency);
  if (!compactCurrencyFormatters.has(code)) {
    compactCurrencyFormatters.set(code, new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: code,
      notation: "compact",
      maximumFractionDigits: 1,
    }));
  }
  return compactCurrencyFormatters.get(code).format(Number(value) || 0);
}
