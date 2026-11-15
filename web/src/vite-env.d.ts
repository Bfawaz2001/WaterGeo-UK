/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_WATERGEO_SERVICE_MANIFEST_SHA256?: string;
  readonly VITE_WATERGEO_SERVICE_BUNDLE_PATH?: string;
  readonly VITE_API_BASE_PATH?: string;
  readonly VITE_BASEMAP_STYLE_URL?: string;
  readonly VITE_WATERGEO_DATA_MODE?: string;
  readonly VITE_WATERGEO_STATIC_DATA_PATH?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
