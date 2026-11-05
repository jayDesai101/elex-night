/// <reference types="vite/client" />

declare module "us-atlas/counties-10m.json" {
  const value: Record<string, unknown>;
  export default value;
}

interface ImportMetaEnv {
  readonly VITE_REPLAY?: string;
  readonly VITE_SITE_URL?: string;
}
