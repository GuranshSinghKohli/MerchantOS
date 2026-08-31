const SHOP = /^[a-z0-9][a-z0-9-]*\.myshopify\.com$/i;

export function normalizeShopDomain(raw: string): string {
  return raw.trim().toLowerCase().replace(/^https?:\/\//, "").replace(/\/.*$/, "");
}

export function isValidShopDomain(raw: string): boolean {
  return SHOP.test(normalizeShopDomain(raw));
}
