// Chromium local; APIs simuladas. Compara a geometria com o HTML anterior ao ajuste.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const {execFileSync} = require('node:child_process');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright-core');
const root = __dirname;
const original = execFileSync('git', ['show', 'HEAD:site-html/teoria.html'], {cwd: root, encoding: 'utf8'});
// Também funciona depois de integrar o incremento, sem carregar o módulo novo na referência.
const baseline = original.replace(/.*(?:css\/teoria-cabecalho\.css|js\/teoria-cabecalho\.js).*\n/g, '');
const servidor = http.createServer((req, res) => {
  const u = new URL(req.url, 'http://local');
  const relativo = u.pathname.replace(/^\/(?:base\/)?/, '');
  const arquivo = path.resolve(root, relativo);
  if (!arquivo.startsWith(root + path.sep) || !fs.existsSync(arquivo)) {res.writeHead(404);res.end();return;}
  res.setHeader('Content-Type', ({'.html':'text/html; charset=utf-8','.css':'text/css','.js':'text/javascript'})[path.extname(arquivo)] || 'application/octet-stream');
  res.end(u.pathname === '/base/teoria.html' ? baseline : fs.readFileSync(arquivo));
});
const usual = {curso:'Guarda Municipal', disciplina:'Direito Constitucional', assunto:'Direitos Fundamentais'};
const cursoLongo = 'Preparatório Completo para o Concurso da Guarda Civil Municipal de São Paulo';
const casos = [
  {nome:'usual', ...usual},
  {nome:'curso longo', ...usual, curso:cursoLongo},
  {nome:'três nomes longos', curso:cursoLongo, disciplina:'Direito Constitucional e Organização Político-Administrativa do Estado Brasileiro', assunto:'Direitos e Garantias Fundamentais: Direitos Individuais, Coletivos e Sociais'},
  {nome:'sem espaços', ...usual, curso:'CursoSemEspacos'.repeat(24)},
  {nome:'caracteres especiais', ...usual, curso:'Curso <img src=x onerror=alert(1)> & Constituição — São Paulo'},
  {nome:'nome recuperado por contexto', ...usual, semNome:true, demonstracao:true, aluno:'Alexandrinaconstantinopolitana Silva'}
];
const medidas = [];
const perto = (a,b,msg) => assert.ok(Math.abs(a-b) < 0.02, `${msg}: ${a} / ${b}`);
async function geometria(p) {
  await p.evaluate(() => window.scrollTo({top:0,behavior:'instant'}));
  return p.evaluate(() => {
    // A leitura usa scrollIntoView suave; compare a geometria na página,
    // independentemente do frame atual da animação da janela.
    const box = el => {const r=el.getBoundingClientRect();return {x:r.x+scrollX,y:r.y+scrollY,w:r.width,h:r.height};};
    return {faixa:box(document.querySelector('header')), botoes:[...document.querySelectorAll('.teoria-header-acoes .btn')].map(box),
      laterais:[...document.querySelectorAll('.botao-estudo-lateral')].map(el => ({id:el.id,handler:el.getAttribute('onclick'),style:getComputedStyle(el).cssText, w:box(el).w,h:box(el).h}))};
  });
}
async function conferir(p, referencia, caso, largura) {
  // Dois frames deixam concluir o ResizeObserver, a identificação compartilhada e o ajuste.
  await p.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));
  const atual = await geometria(p);
  for (const chave of ['x','y','w','h']) perto(atual.faixa[chave],referencia.faixa[chave],`faixa ${largura} ${chave}`);
  atual.botoes.forEach((botao,i) => Object.keys(botao).forEach(k => perto(botao[k],referencia.botoes[i][k],`botão ${i} ${largura} ${k}`)));
  assert.deepEqual(atual.laterais,referencia.laterais,'Dimensões e handlers dos controles laterais');
  const estado = await p.evaluate(() => {
    const contexto = document.querySelector('.teoria-contexto');
    const r=contexto.getBoundingClientRect(), faixa=document.querySelector('header').getBoundingClientRect();
    const interno=contexto.parentElement.tagName==='HEADER';
    const textos=[...contexto.children];
    const caixas=textos.filter(el=>!el.hidden).map(el=>el.getBoundingClientRect());
    const font=textos.map(el=>getComputedStyle(el));
    const controles=[...document.querySelectorAll('.teoria-header-acoes .btn,.ro-header-identity')].map(el=>el.getBoundingClientRect());
    const intersecta=(a,b)=>a.left<b.right-.01&&a.right>b.left+.01&&a.top<b.bottom-.01&&a.bottom>b.top+.01;
    return {interno,textos:textos.map(el=>el.textContent),fontes:font.map(s=>parseFloat(s.fontSize)),peso:font[0].fontWeight,
      semCortes:textos.every(el=>el.scrollWidth<=el.clientWidth+1&&el.scrollHeight<=el.clientHeight+1),
      semRolagem:contexto.scrollWidth<=contexto.clientWidth+1&&contexto.scrollHeight<=contexto.clientHeight+1,
      semSobreposicao:caixas.every((a,i)=>!i||a.top>=caixas[i-1].bottom-.01)&&(!interno||controles.every(b=>!intersecta(r,b))),
      dentro:!interno||(r.top>=faixa.top&&r.bottom<=faixa.bottom),
      abaixo:interno||(contexto.previousElementSibling.tagName==='HEADER'&&Math.abs(r.top-faixa.bottom)<.02),
      larguraCorreta:r.left>=0&&r.right<=innerWidth+.02,
      cursoInjetouHTML:Boolean(textos[0].querySelector('*')),
      origemOculta:document.querySelector('.teoria-header-identificacao').getAttribute('aria-hidden')==='true'};
  });
  assert.deepEqual(estado.textos,[caso.curso,caso.disciplina,caso.assunto]);
  for (const k of ['semCortes','semRolagem','semSobreposicao','dentro','abaixo','larguraCorreta','origemOculta']) assert.ok(estado[k],`${caso.nome} ${largura}: ${k}`);
  assert.ok(estado.fontes.every(n=>n>=12), 'Fonte mínima');
  assert.equal(estado.peso,'700');
  assert.equal(estado.cursoInjetouHTML,false);
  if (!estado.interno) perto(estado.fontes[0],largura<=480?16:20.8,'Fonte original no bloco externo');
  if (caso.nome==='usual') perto(estado.fontes[0],largura<=480?16:20.8,'Fonte original quando cabe');
  medidas.push({largura,caso:caso.nome,interno:estado.interno,fontes:estado.fontes,altura:atual.faixa.h});
  return estado;
}
(async () => {
  let browser;
  const erros = [];
  try {
    await new Promise(r=>servidor.listen(0,'127.0.0.1',r));
    const origem=`http://127.0.0.1:${servidor.address().port}`;
    browser=await chromium.launch({executablePath:process.env.CHROMIUM_BIN || '/home/codespace/.cache/ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-linux64/chrome-headless-shell',args:['--no-sandbox']});
    async function abrir(caso,largura,base=false) {
      const p=await browser.newPage({viewport:{width:largura,height:900}});
      p.on('pageerror',e=>erros.push(e.message));
      await p.addInitScript(()=>localStorage.setItem('access_token','token-sintetico'));
      await p.route('**/*',async route=>{
        const url=route.request().url();
        if(url.startsWith(origem))return route.continue();
        const u=new URL(url);
        if(u.origin!=='https://plataforma-quality-backend.onrender.com')return route.abort();
        let json=[];
        if(u.pathname==='/me') {await new Promise(r=>setTimeout(r,60));json={id:1,nome:caso.aluno||'Maria Silva',ativo:true};}
        if(u.pathname==='/me/cursos')json=[{curso_id:1,contratacao_id:caso.demonstracao?null:1,demonstracao_id:caso.demonstracao?1:null,nome_curso:caso.curso}];
        if(u.pathname==='/pastas/1/aulas')json=[{id:1,titulo:'Aula',ordem:1}];
        if(u.pathname==='/aulas/1/materiais')json=[{tipo:'TEXTO',conteudo:('Texto de regressão. '.repeat(40)+'\n\n').repeat(8)}];
        await route.fulfill({json,headers:{'Access-Control-Allow-Origin':'*'}});
      });
      const q=new URLSearchParams({pasta_id:1,curso_id:1,disciplina_id:1,assunto_id:1,disciplina_nome:caso.disciplina,assunto_nome:caso.assunto});
      q.set(caso.demonstracao?'demonstracao_id':'contratacao_id','1');
      if(!caso.semNome)q.set('curso_nome',caso.curso);
      await p.goto(origem+(base?'/base':'')+'/teoria.html?'+q);
      await p.waitForFunction(()=>document.querySelector('.teoria-paragrafo')&&document.querySelector('.ro-identity'));
      if(!base)await p.waitForFunction(curso=>document.querySelector('.teoria-contexto-curso')?.textContent===curso,caso.curso);
      await p.evaluate(()=>document.fonts.ready);
      return p;
    }
    for(const largura of [1280,768,390,320])for(const caso of casos){
      const base=await abrir(caso,largura,true), p=await abrir(caso,largura);
      const referencia=await geometria(base);
      await conferir(p,referencia,caso,largura);
      // Foco por teclado e funcionamento dos três modos existentes.
      await p.keyboard.press('Tab');
      assert.equal(await p.locator('.teoria-header-acoes .btn').first().evaluate(el=>el===document.activeElement),true);
      const paginacao=await p.locator('#paginacao_teoria').innerText();
      assert.match(paginacao,/^1\/[2-9]/);
      await p.evaluate(()=>window.proximaPaginaTeoria());
      assert.match(await p.locator('#paginacao_teoria').innerText(),/^2\//);
      await p.evaluate(()=>document.querySelector('#btn_video').click());
      await p.locator('.video-vazio').waitFor();
      assert.equal(await p.locator('#btn_video').getAttribute('class'),'botao-estudo-lateral ativo');
      await p.evaluate(()=>document.querySelector('#btn_questoes').click());
      await p.waitForFunction(()=>!document.querySelector('#detalhes_aula').textContent.includes('Carregando'));
      assert.ok(await p.locator('#btn_questoes').evaluate(el=>el.classList.contains('ativo')));
      await p.evaluate(()=>document.querySelector('#btn_teoria').click());
      await p.locator('.teoria-paragrafo').first().waitFor();
      assert.ok(await p.locator('#btn_teoria').evaluate(el=>el.classList.contains('ativo')));
      await conferir(p,referencia,caso,largura);
      if(process.env.HEADER_SCREENSHOTS){fs.mkdirSync(process.env.HEADER_SCREENSHOTS,{recursive:true});await p.screenshot({path:path.join(process.env.HEADER_SCREENSHOTS,`${largura}-${casos.indexOf(caso)}.png`)});}
      await base.close();await p.close();
    }
    // Redimensiona a mesma página: inclui a volta do bloco externo para a faixa.
    const caso=casos[1], p=await abrir(caso,1280);
    const modos=[];
    for(const largura of [1280,768,390,320,390,768,1280,320]){
      await p.setViewportSize({width:largura,height:900});
      const base=await abrir(caso,largura,true);
      modos.push((await conferir(p,await geometria(base),caso,largura)).interno);
      await base.close();
    }
    assert.ok(modos.includes(true)&&modos.includes(false),'Alterna apresentação no resize');
    await p.close();
    assert.deepEqual(erros,[],'Erros JavaScript');
    if(process.env.HEADER_RESULTS)fs.writeFileSync(process.env.HEADER_RESULTS,JSON.stringify(medidas,null,2));
    console.log(`OK: ${casos.length*4} cenários, três modos, paginação, foco e oito redimensionamentos; faixa e botões idênticos à referência.`);
    console.log(JSON.stringify(medidas.filter((_,i)=>i<casos.length*4*2&&i%2===0)));
  } finally {await browser?.close();await new Promise(r=>servidor.close(r));}
})().catch(e=>{console.error(e);process.exitCode=1;});
