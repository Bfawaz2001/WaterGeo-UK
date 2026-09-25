/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_PATH?: string;
  readonly VITE_BASEMAP_STYLE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
