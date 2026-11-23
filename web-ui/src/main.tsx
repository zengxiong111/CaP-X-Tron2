import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import { Tron2Workflow } from './components/Tron2Workflow'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    {/^\/tron2\/?$/.test(window.location.pathname) ? <Tron2Workflow /> : <App />}
  </React.StrictMode>,
)
