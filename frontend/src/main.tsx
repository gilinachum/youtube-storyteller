// Polyfill `global` for libraries that expect Node.js environment (e.g. amazon-cognito-identity-js)
if (typeof globalThis !== 'undefined' && !(globalThis as Record<string, unknown>).global) {
  (globalThis as Record<string, unknown>).global = globalThis;
}

import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)
