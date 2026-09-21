import React from 'react';
import { createRoot, hydrateRoot } from 'react-dom/client';
import App from './App.jsx';
import './style.css';

const parts = window.location.pathname.split('/').filter(Boolean);
const lang = parts[0] === 'en' ? 'en' : 'de';
const page = ['privacy', 'terms'].includes(parts[1]) ? parts[1] : 'home';
const root = document.getElementById('root');
const app = <App lang={lang} page={page}/>;
if (root.hasChildNodes()) hydrateRoot(root, app); else createRoot(root).render(app);
