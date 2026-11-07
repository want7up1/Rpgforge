/** 与服务端玩家投影使用相同的私有可见性别名，历史字段也在此归一。 */
const PRIVATE_VISIBILITY = new Set([
  "hidden", "secret", "unknown", "gm", "gm_only", "director", "director_only", "internal", "private",
  "隐藏", "秘密", "未知", "幕后", "主持人"
]);

export function isPrivateVisibility(value: unknown): boolean {
  return typeof value === "string" && PRIVATE_VISIBILITY.has(value.trim().toLowerCase());
}
