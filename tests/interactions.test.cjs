// Offline regression checks. No network, browser navigation or form submissions.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const page = fs.readFileSync('editions/2026-11-06.html', 'utf8');
const script = [...page.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g)][0][1];
const answer = +page.match(/data-answer="(\d)"/)[1];
assert.equal(answer, 1);
function trivia(search, previous = null, storageFails = false) {
  let stored = previous, scrolls = 0;
  const classes = new Set();
  const rows = Array.from({length: 4}, () => ({
    disabled: false, classes: new Set(),
    classList: {add(value) { this.owner.classes.add(value); }},
    addEventListener(_, callback) { this.click = callback; },
  }));
  rows.forEach(r => r.classList.owner = r);
  const reveal = {hidden: true}, verdict = {textContent: ''};
  const card = {
    classList: {contains: c => classes.has(c), add: c => classes.add(c)},
    getAttribute: () => String(answer),
    querySelectorAll: () => rows,
    querySelector: s => s === '.qz-verdict' ? verdict : reveal,
    scrollIntoView: () => scrolls++,
  };
  vm.runInNewContext(script, {
    document: {getElementById: () => card},
    location: {search, pathname: '/editions/2026-11-06.html'},
    URLSearchParams, setTimeout: f => f(),
    localStorage: {
      getItem(key) { assert.equal(key, 'ffd-qz-/editions/2026-11-06.html'); if (storageFails) throw Error(); return stored; },
      setItem(_, value) { if (storageFails) throw Error(); stored = String(value); },
    },
  });
  return {rows, reveal, verdict, classes, stored: () => stored, scrolls: () => scrolls};
}
let cases = 0;
for (const search of ['', '?pick=', '?pick=E', '?pick=AB', '?pick=1', '?pick=%20', '?unrelated=A']) {
  const t = trivia(search);
  assert.equal(t.reveal.hidden, true, search);
  assert.equal(t.classes.has('done'), false);
  assert.ok(t.rows.every(r => !r.disabled));
  assert.equal(t.stored(), null);
  cases++;
}
for (const letter of 'ABCDabcd') {
  const t = trivia('?pick=' + letter), i = 'ABCD'.indexOf(letter.toUpperCase());
  assert.equal(t.reveal.hidden, false);
  assert.equal(t.verdict.textContent, i === answer ? 'Correct!' : 'Not quite.');
  assert.equal(t.stored(), String(i));
  assert.ok(t.rows.every(r => r.disabled));
  assert.ok(t.rows[answer].classes.has('ok'));
  if (i !== answer) assert.ok(t.rows[i].classes.has('no'));
  assert.equal(t.scrolls(), 1);
  t.rows[(i + 1) % 4].click();
  assert.equal(t.stored(), String(i), 'One answer per browser/path');
  cases++;
}
const restored = trivia('?pick=A', '1');
assert.equal(restored.stored(), '1');
assert.equal(restored.verdict.textContent, 'Correct!');
assert.equal(restored.scrolls(), 0);
cases++;
const noStorage = trivia('?pick=B', null, true);
assert.equal(noStorage.verdict.textContent, 'Correct!');
cases++;
const clicked = trivia('');
clicked.rows[2].click();
assert.equal(clicked.verdict.textContent, 'Not quite.');
assert.equal(clicked.stored(), '2');
cases++;
const home = fs.readFileSync('index.html', 'utf8');
const homeScript = [...home.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g)].at(-1)[1];
// Evaluate configuration only: deliberately never invoke signup/submit handlers.
const config = vm.runInNewContext(homeScript.slice(0, homeScript.indexOf('function isPublicHttps')) + '\nSITE_CONFIG;');
assert.equal(config.editions[0].date, '2026-11-12');
assert.equal(config.editions[0].url, 'https://factsfirstdaily.com/editions/2026-11-12.html');
assert.equal(config.editions.length, 12);
for (const entry of config.editions) assert.ok(fs.existsSync(new URL(entry.url).pathname.slice(1)));
assert.equal(config.mailerliteFormAction, 'https://assets.mailerlite.com/jsonp/2756267/forms/203044673267173156/subscribe');
assert.equal(config.mailerliteSignupUrl, '');
assert.equal(config.privacyPolicyUrl, 'https://factsfirstdaily.com/privacy.html');
console.log(`PASS: ${cases} trivia scenarios; homepage configuration and all 12 edition destinations. No requests made.`);
