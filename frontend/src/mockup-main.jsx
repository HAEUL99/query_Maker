import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import MockupPage from './MockupPage.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <MockupPage />
  </StrictMode>,
)
