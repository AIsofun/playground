/**
 * 运行时读取 Vite 环境变量（§5.1：禁止硬编码 API / WS 根地址）。
 */
export function getApiBaseUrl(): string {
  return (import.meta.env.VITE_API_BASE_URL ?? "").trim();
}

export function getWsBaseUrl(): string {
  return (import.meta.env.VITE_WS_BASE_URL ?? "").trim();
}
