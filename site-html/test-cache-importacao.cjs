const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

test('todos os consumidores dos scripts alterados usam a versão da implantação', () => {
  const root = __dirname;
  const assets = ['app.js','admin.js','admin-criar-curso-completo.js','admin-importar-curso.js'];
  const seen = new Set();
  function visitar(dir) {
    for (const e of fs.readdirSync(dir, {withFileTypes:true})) {
      const p=path.join(dir,e.name);
      if (e.isDirectory()) visitar(p);
      else if (e.name.endsWith('.html')) {
        const html=fs.readFileSync(p,'utf8');
        for (const m of html.matchAll(/(?:\.\.\/)?js\/([\w-]+\.js)(\?[^"\s]*)?(?=["\s])/g)) {
          if (!assets.includes(m[1])) continue;
          seen.add(m[1]);
          assert.equal(m[2], '?v=importacao-20261120-1', `${p}: ${m[1]}`);
        }
      }
    }
  }
  visitar(root);
  assert.deepEqual([...seen].sort(), [...assets].sort());
});
