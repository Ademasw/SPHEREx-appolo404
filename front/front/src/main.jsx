/**
 * src/main.jsx — application entry point.
 *
 * Style import ORDER matters:
 *   1. theme.css      -> colour + animation-speed variables
 *   2. typography.css -> font variables + .text-* classes
 *   3. global.css     -> reset / base elements (uses the variables above)
 */
import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';

import './styles/theme.css';
import './styles/typography.css';
import './styles/global.css';

import App from './App.jsx';

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
);

