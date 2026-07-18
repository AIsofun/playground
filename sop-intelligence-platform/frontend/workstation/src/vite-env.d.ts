/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_WS_BASE_URL?: string;
  /** 演示页 / Mock 视频绝对或相对 URL（优先于内置默认与本地文件） */
  readonly VITE_DEMO_VIDEO_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
