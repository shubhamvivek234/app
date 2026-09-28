const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const pages = [
  'index.html',
  'features.html',
  'feature-sequences.html',
  'feature-leads.html',
  'feature-engage.html',
  'feature-personalization.html',
  'feature-inbox.html',
  'feature-safety.html',
  'feature-analytics.html',
  'feature-teams.html',
  'pricing.html',
  'integrations.html',
  '404.html',
  'privacy.html',
  'terms.html',
  'refunds.html',
  'cookies.html',
  'data-deletion.html',
  'contact.html',
];

function read(file) {
  return fs.readFileSync(path.join(root, file), 'utf8');
}

test('all public pages are complete, navigable HTML documents', () => {
  for (const page of pages) {
    const html = read(page);
    assert.match(html, /<!doctype html>/i, `${page} needs a doctype`);
    assert.match(html, /<html[^>]+lang="en"/i, `${page} needs an English language`);
    assert.match(html, /<meta[^>]+name="viewport"/i, `${page} needs a mobile viewport`);
    assert.match(html, /<meta[^>]+name="description"/i, `${page} needs a description`);
    assert.match(html, /<main\b/i, `${page} needs a main landmark`);
    assert.match(html, /<footer\b/i, `${page} needs a footer`);
    assert.equal((html.match(/<h1\b/gi) || []).length, 1, `${page} needs one H1`);
    assert.match(html, /href="privacy\.html"/i, `${page} should link the privacy notice`);
    assert.match(html, /href="terms\.html"/i, `${page} should link the terms`);

    for (const [, raw] of html.matchAll(/(?:href|src)="([^"]+)"/g)) {
      if (/^(?:https?:|mailto:|tel:|data:)/.test(raw)) continue;
      const [target, fragment] = raw.split('#');
      if (!target) {
        if (fragment) assert.match(html, new RegExp(`id="${fragment}"`), `${page} has a missing anchor: ${raw}`);
        continue;
      }
      assert.ok(fs.existsSync(path.join(root, target)), `${page} has a broken local link: ${raw}`);
      if (fragment && target.endsWith('.html')) {
        assert.match(read(target), new RegExp(`id="${fragment}"`), `${page} has a missing anchor: ${raw}`);
      }
    }
  }
});

test('landing page names real workflow and openly identifies pilot availability', () => {
  const html = read('index.html');
  for (const term of ['campaign', 'lead', 'inbox', 'engage', 'invite-only']) {
    assert.match(html, new RegExp(term, 'i'));
  }
  assert.match(html, /assets\/unravler-logo-dark\.png/);
  assert.match(html, /assets\/hero-ribbons\.jpg/);
  assert.match(html, /role="tablist"/);
  assert.match(html, /aria-controls="panel-engage"/);
  assert.doesNotMatch(html, /data-panel="(?:engage|inbox|measure)" hidden/);
  assert.match(read('site.js'), /activateTab\(tabs\[0\]\)/);
  assert.doesNotMatch(html, /guaranteed results|linkedin-approved|risk-free automation|start (?:your )?free trial|try for free/i);
});

test('pricing matches the operator-gated pilot rather than a nonexistent checkout', () => {
  const html = read('pricing.html');
  assert.match(html, /\$59/);
  assert.match(html, /per sender|sender \/ month|sender\/month/i);
  assert.match(html, /invoice|manual billing|operator/i);
  assert.match(html, /invite-only/i);
  assert.doesNotMatch(html, /start (?:your )?free trial|checkout now|pay now/i);
});

test('marketing pages disclose session and platform risk instead of promising compliance', () => {
  const html = pages.map(read).join('\n');
  assert.match(html, /session cookie|session token/i);
  assert.match(html, /account restriction|account suspension/i);
  assert.match(html, /unauthori[sz]ed|unofficial/i);
  assert.doesNotMatch(html, /100% compliant|avoid bans|ban-proof/i);
});

test('shared motion respects reduced-motion preferences', () => {
  assert.match(read('styles.css'), /prefers-reduced-motion:\s*reduce/);
  assert.match(read('site.js'), /IntersectionObserver/);
});

test('features mega menu contains links to all dedicated feature pages and directory', () => {
  const indexHtml = read('index.html');
  assert.match(indexHtml, /class="nav-item nav-item-dropdown"/);
  assert.match(indexHtml, /class="nav-dropdown-trigger"/);
  assert.match(indexHtml, /id="features-mega-menu"/);

  const expectedFeaturePages = [
    'feature-sequences.html',
    'feature-leads.html',
    'feature-engage.html',
    'feature-personalization.html',
    'feature-inbox.html',
    'feature-safety.html',
    'feature-analytics.html',
    'feature-teams.html',
    'features.html',
  ];

  for (const page of expectedFeaturePages) {
    assert.match(indexHtml, new RegExp(`href="${page}"`), `Mega menu should link to ${page}`);
    const featureHtml = read(page);
    assert.match(featureHtml, /<h1\b/, `${page} must have an H1 title`);
    assert.match(featureHtml, /contact\.html/, `${page} must offer pilot access CTA`);
  }

  // Ensure JS includes dropdown click and hover handling
  const js = read('site.js');
  assert.match(js, /\.nav-item-dropdown/);
  assert.match(js, /aria-expanded/);
  assert.match(js, /Escape/);
});

