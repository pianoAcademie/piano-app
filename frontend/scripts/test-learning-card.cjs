// Run in an isolated frontend container with jsdom installed; no server or real student writes.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const Module = require('node:module');
const path = require('node:path');
const ts = require('typescript');
const { JSDOM } = require('jsdom');
const dom = new JSDOM('<!doctype html><div id="root"></div>', { url: 'http://localhost' });
global.window = dom.window;
global.document = dom.window.document;
global.navigator = dom.window.navigator;
global.HTMLElement = dom.window.HTMLElement;
global.IS_REACT_ACT_ENVIRONMENT = true;
const React = require('react');
const { createRoot } = require('react-dom/client');
const { act } = require('react-dom/test-utils');
let saved;
const externalId = 'f41669ea-c081-45be-9e4f-06a71eb44ae3';
const filename = path.resolve('components/teacher-ui/learning-card.tsx');
const compiled = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
}).outputText;
const loaded = new Module(filename, module);
loaded.filename = filename;
loaded.paths = Module._nodeModulePaths(path.dirname(filename));
const originalRequire = loaded.require.bind(loaded);
loaded.require = (id) => {
  if (id.endsWith('learning-actions')) return { learningAction: async (_student, _session, command) => {
    saved = command;
    return { ok: true, data: { revision: 1, state: { product_id: externalId, books: {
      [externalId]: { external: true, title: command.external_title, composer: command.external_composer,
        note: command.note, completed: false, current_piece_id: externalId, pieces: {} },
    } } } };
  } };
  if (id.endsWith('.css')) return new Proxy({}, { get: (_, key) => key });
  return originalRequire(id);
};
loaded._compile(compiled, filename);
const LearningCard = loaded.exports.default;
const root = createRoot(document.getElementById('root'));
const button = (label) => [...document.querySelectorAll('button')].find(b => b.textContent === label);

async function run() {
  await act(async () => root.render(React.createElement(LearningCard, {
    studentId: externalId, studentName: 'Élève test', sessionId: externalId,
    catalog: [{ product_id: 'school', title: 'Partition degré 1', pieces: [{ id: 'one', title: 'Morceau 1' }] }],
    initial: { revision: 0, state: { product_id: 'school', books: { school: { current_piece_id: 'one', completed: false, pieces: {} } } } },
  })));
  const change = button('Changer la partition / le morceau');
  assert.ok(change, 'Le bouton doit être immédiatement disponible');
  assert.equal(change.closest('details'), null, 'Le bouton ne doit pas être caché dans un accordéon');
  await act(async () => change.click());
  const select = document.querySelector('select');
  assert.ok([...select.options].some(o => o.textContent === 'Autre partition / morceau hors catalogue'));
  await act(async () => { select.value = 'external-new'; select.dispatchEvent(new window.Event('change', { bubbles: true })); });
  const inputs = [...document.querySelectorAll('fieldset input')];
  assert.equal(inputs.length, 2);
  assert.ok(inputs[0].required);
  async function fill(input, value) {
    await act(async () => {
      Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set.call(input, value);
      input.dispatchEvent(new window.Event('input', { bubbles: true }));
    });
  }
  await fill(inputs[0], 'Imagine');
  await fill(inputs[1], 'John Lennon');
  await act(async () => document.querySelector('form').dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true })));
  assert.equal(saved.external_title, 'Imagine');
  assert.equal(saved.external_composer, 'John Lennon');
  assert.equal(saved.product_id, null);
  assert.match(document.body.textContent, /Imagine — John Lennon · hors catalogue/);
  assert.ok(button('Continuer ce morceau'));
  await act(async () => button('Changer la partition / le morceau').click());
  assert.equal(document.querySelector('fieldset input').value, 'Imagine', 'Le titre doit rester modifiable');
  await act(async () => root.unmount());
  console.log('PASS: bouton visible, choix hors catalogue, saisie libre, enregistrement et modification');
}
run().catch(error => { console.error(error); process.exitCode = 1; });
