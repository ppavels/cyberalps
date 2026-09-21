// Run in GitHub CI against the built application. No third-party sites are contacted.
import { chromium } from 'playwright';
import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';

await mkdir('reports', { recursive: true });
const browser = await chromium.launch();
try {
  for (const [name, width, height] of [['desktop', 1440, 1000], ['mobile', 390, 844], ['small-mobile', 320, 780]]) {
    for (const language of ['de', 'en']) {
      const context = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: 1, reducedMotion: 'reduce' });
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.goto(`http://127.0.0.1:3002/${language}/`, { waitUntil: 'networkidle' });
      assert.equal(await page.locator('h1').count(), 1);
      assert.ok(await page.locator('#url').isVisible());
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${name}/${language} overflows`);
      await page.screenshot({ path: `reports/${name}-${language}.png`, fullPage: true });
      if (width < 760) {
        const menu = page.getByRole('button', { name: 'Menu', exact: true });
        await menu.click();
        assert.equal(await page.locator('nav.open').count(), 1);
        await page.locator('nav button').click();
      } else {
        await page.locator('nav button').click();
      }
      await page.locator('dialog[open]').waitFor();
      await page.locator('input[name="name"]').fill('CI Test Client');
      await page.locator('input[name="email"]').fill('ci@example.com');
      await page.locator('textarea[name="message"]').fill('This is an automated local form check.');
      await page.locator('input[name="consent"]').check();
      // Each context uses a distinct forwarded test IP; the production proxy overwrites this header.
      await page.route('**/api/leads', route => route.continue({ headers: { ...route.request().headers(), 'x-real-ip': `192.0.2.${width === 1440 ? 1 : width === 390 ? 2 : 3}` } }));
      await page.locator('form.contact-form button[type="submit"], form.contact-form button:not([type])').click();
      await page.locator('.success').waitFor();
      await page.keyboard.press('Escape');
      await page.locator('#url').fill('http://127.0.0.1');
      await page.locator('.audit-form input[type="checkbox"]').check();
      await page.locator('.audit-form button').click();
      await page.locator('.hero-copy [role="alert"]').waitFor();
      assert.match(await page.locator('.hero-copy [role="alert"]').innerText(), /public HTTP/);
      assert.deepEqual(errors, [], `${name}/${language} JavaScript errors`);
      await context.close();
    }
  }
} finally {
  await browser.close();
}
console.log('Desktop, mobile, forms, hydration and private-address rejection passed.');
