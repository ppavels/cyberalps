import { readFile, writeFile, mkdir, rm } from 'node:fs/promises';
import { render, content } from '../dist/ssr/entry-server.js';
const shell = await readFile('dist/index.html', 'utf8');
const escape = value => value.replaceAll('&','&amp;').replaceAll('"','&quot;').replaceAll('<','&lt;');
for (const lang of ['de','en']) {
  for (const page of ['home','privacy','terms']) {
    const suffix = page === 'home' ? '' : page + '/';
    const path = `/${lang}/${suffix}`;
    const title = page === 'home' ? content[lang].title : `${page === 'privacy' ? content[lang].privacy : content[lang].terms} | CyberAlps`;
    const seo = `<meta name="description" content="${escape(content[lang].description)}"/><link rel="canonical" href="__PUBLIC_ORIGIN__${path}"/><link rel="alternate" hreflang="de-CH" href="__PUBLIC_ORIGIN__/de/${suffix}"/><link rel="alternate" hreflang="en" href="__PUBLIC_ORIGIN__/en/${suffix}"/><link rel="alternate" hreflang="x-default" href="__PUBLIC_ORIGIN__/de/${suffix}"/><meta property="og:title" content="${escape(title)}"/><meta property="og:description" content="${escape(content[lang].description)}"/><meta property="og:type" content="website"/><meta property="og:url" content="__PUBLIC_ORIGIN__${path}"/><meta property="og:image" content="__PUBLIC_ORIGIN__/alps.webp"/>`;
    const html = shell.replace('<html lang="de">', `<html lang="${lang}">`).replace('<title>CyberAlps</title>', `<title>${escape(title)}</title>`).replace('<!--seo-->', seo).replace('<!--app-html-->', render(lang,page));
    const target = `dist${path}`;
    await mkdir(target,{recursive:true});
    await writeFile(target+'index.html',html);
    if (lang === 'de' && page === 'home') await writeFile('dist/index.html',html);
  }
}
await rm('dist/ssr',{recursive:true,force:true});
console.log('Prerendered six crawlable pages.');
