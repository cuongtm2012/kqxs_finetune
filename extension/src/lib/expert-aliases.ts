/** Alias forum → tài khoản chính (cùng người, tránh cộng điểm 2 lần). */
const EXPERT_ALIASES: Record<string, string> = {
  "lokhata 1789": "nhcsxh",
  lokhata1789: "nhcsxh",
};

export function canonicalUsername(username: string): string {
  const key = username.trim();
  if (!key) return key;
  return EXPERT_ALIASES[key.toLowerCase()] || key;
}
