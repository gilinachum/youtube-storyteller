/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_AUTH_MODE: 'cognito' | 'federate'
  readonly VITE_APP_VERSION: string
  readonly VITE_API_URL: string
  readonly VITE_WS_URL?: string
  readonly VITE_COGNITO_USER_POOL_ID?: string
  readonly VITE_COGNITO_CLIENT_ID?: string
  readonly VITE_FEDERATE_DISCOVERY_URL?: string
  readonly VITE_FEDERATE_CLIENT_ID?: string
  readonly VITE_FEDERATE_REDIRECT_URI?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
