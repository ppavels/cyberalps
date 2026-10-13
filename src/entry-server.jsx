import React from 'react';
import { renderToString } from 'react-dom/server';
import App from './App.jsx';
export { content } from './content.js';
export { developmentCopy } from './developmentCopy.js';
export const render = (lang, page) => renderToString(<App lang={lang} page={page}/>);
