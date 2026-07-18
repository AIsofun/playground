/** 拼接 base 与 path，规范去除多余斜杠 */
export function joinBaseUrl(base: string, path: string): string {
  const b = base.replace(/\/+$/, "");
  const p = path.startsWith("/") ? path : `/${path}`;
  return `${b}${p}`;
}
