// Home real no Chromium, com APIs simuladas. Nunca acessa Render ou pagamentos reais.
// PLAYWRIGHT_MODULE e CHROMIUM_BIN permitem reutilizar o navegador local.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = __dirname;
const artifacts = process.env.HOME_TEST_ARTIFACTS;
const courses = [
  {id: 1, nome: 'RESUMÃO PROFESSOR EDUCAÇÃO INFANTIL ALVORADA-RS 2026', ativo: true},
  {id: 2, nome: 'RESUMÃO AGENTE COMUNITÁRIO DE SAÚDE PORTO ALEGRE-RS 2026', ativo: true},
  {id: 3, nome: 'RESUMÃO TÉCNICO JUDICIÁRIO 2026', ativo: true},
  {id: 4, nome: 'RESUMÃO ASSISTENTE ADMINISTRATIVO 2026', ativo: true},
  {id: 5, nome: 'RESUMÃO PROFESSOR MATEMÁTICA 2026', ativo: true},
  {id: 6, nome: 'RESUMÃO FISCAL 2026', ativo: true},
  {id: 7, nome: 'Curso inativo', ativo: false}
];
const server = http.createServer((req, res) => {
  const file = path.resolve(root, '.' + new URL(req.url, 'http://localhost').pathname);
  if (!file.startsWith(root + path.sep) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
    res.writeHead(404).end(); return;
  }
  res.setHeader('Content-Type', ({'.html':'text/html; charset=utf-8', '.css':'text/css', '.js':'application/javascript', '.woff2':'font/woff2', '.svg':'image/svg+xml'})[path.extname(file)] || 'application/octet-stream');
  res.end(fs.readFileSync(file));
});

(async () => {
  let browser;
  try {
    if (artifacts) fs.mkdirSync(artifacts, {recursive: true});
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    const origin = `http://127.0.0.1:${server.address().port}`;
    browser = await chromium.launch({executablePath: process.env.CHROMIUM_BIN, args: ['--no-sandbox']});
    const measurements = [];
    async function context(width, user = null, data = courses, fail = false) {
      const ctx = await browser.newContext({viewport: {width, height: 900}, reducedMotion: 'reduce'});
      if (user) await ctx.addInitScript(() => { if (!sessionStorage.getItem('fixture-initialized')) { localStorage.setItem('access_token', 'token-ficticio'); localStorage.setItem('pagina_antes_inicio', 'cursos.html'); sessionStorage.setItem('fixture-initialized','1'); } });
      await ctx.route('**/*', async route => {
        const u = new URL(route.request().url());
        if (u.origin === origin) return route.continue();
        if (u.origin !== 'https://plataforma-quality-backend.onrender.com') return route.abort();
        const payload = u.pathname === '/cursos-publicos' ? data : u.pathname === '/me' ? user : [];
        await route.fulfill({status: fail && u.pathname === '/cursos-publicos' ? 503 : 200, json: payload});
      });
      return ctx;
    }
    function noOverflow(page) {
      return page.evaluate(() => document.documentElement.scrollWidth <= innerWidth);
    }
    for (const width of [320, 390, 768, 1366]) {
      for (const signedIn of [false, true]) {
        const user = signedIn ? {id: 1, nome: 'Alexandre de Oliveira Administrador', ativo: true, is_aluno: true, is_admin: true, tipo_admin: 'admin_geral'} : null;
        const ctx = await context(width, user);
        const page = await ctx.newPage();
        const errors = []; page.on('pageerror', e => errors.push(e.message));
        await page.goto(origin + '/index.html');
        await page.locator('.curso-publico-card').first().waitFor();
        if (signedIn) await page.locator('.ro-header-identity').waitFor();
        assert.equal(await page.locator('.curso-publico-card').count(), 4);
        assert.equal(await page.locator('.home-course-meta').count(), 0, 'Não deve inventar metadados');
        const sorted = courses.filter(c => c.ativo).sort((a,b) => a.nome.localeCompare(b.nome));
        assert.deepEqual(await page.locator('.curso-publico-nome').allTextContents(), sorted.slice(0,4).map(c => c.nome));
        assert.equal(await page.locator('.curso-publico-card').first().getAttribute('href'), `curso-info.html?curso_id=${sorted[0].id}&curso_nome=${encodeURIComponent(sorted[0].nome)}`);
        const geometry = await page.evaluate(() => {
          const r = e => {const b=e.getBoundingClientRect();return {x:b.x,y:b.y,w:b.width,h:b.height};};
          return {
            brand: r(document.querySelector('.home-brand-title')),
            header: r(document.querySelector('.home-header')),
            name: r(document.querySelector('.home-brand-name')),
            tagline: r(document.querySelector('.home-brand-tagline')),
            book: r(document.querySelector('.home-brand-symbol')),
            identity: document.querySelector('.ro-header-identity') ? r(document.querySelector('.ro-header-identity')) : null,
            access: r(document.querySelector('.ro-header-access a')),
            controls: [...document.querySelectorAll('.ro-header-navigation a')].filter(e=>e.getClientRects().length).map(r),
            font: parseFloat(getComputedStyle(document.querySelector('.ro-header-access a')).fontSize),
            paddingTop: parseFloat(getComputedStyle(document.querySelector('.home-header')).paddingTop),
            width: innerWidth
          };
        });
        assert.ok(Math.abs(geometry.brand.x + geometry.brand.w/2 - width/2) < 1);
        const center = r => r.x+r.w/2;
        assert.ok(Math.abs(center(geometry.access)-center(geometry.name)) < 0.5, 'Minha Área centralizado no texto da marca');
        assert.ok(Math.abs(center(geometry.tagline)-center(geometry.name)) < 0.5, 'Slogan centralizado no nome');
        assert.ok(Math.abs(geometry.name.x-(geometry.book.x+geometry.book.w)-(width<=600?8:14)) < 0.5, 'Espaço entre livro e nome preservado');
        assert.equal(geometry.font,width<=600?17:18);
        assert.equal(geometry.book.w,width<=600?49:73.5);
        assert.equal(geometry.book.h,width<=600?47.25:66.5);
        const courseBook=await page.locator('.home-course-icon img').first().boundingBox();
        assert.equal(courseBook.width,width<=370?31.5:width<=600?38.5:56,'Livro dos cartões reduzido em 12,5%');
        assert.equal(courseBook.height,width<=370?31.5:width<=600?36.75:50.75);
        geometry.courseBook=courseBook;
        if(signedIn){
          assert.ok(geometry.identity.y+geometry.identity.h<=geometry.brand.y,'Identificação acima da marca, sem sobreposição');
          assert.equal(await page.locator('.ro-identity').evaluate(e=>getComputedStyle(e).minHeight),'0px');
          await page.locator('.ro-identity').hover();
          assert.equal(await page.locator('.ro-identity').evaluate(e=>getComputedStyle(e,'::after').visibility),'visible');
          assert.equal((await page.locator('.home-brand-title').boundingBox()).y,geometry.brand.y,'Hover não cria espaço reservado');
          await page.mouse.move(0,0);
        }
        assert.equal(geometry.paddingTop,width<=600?2:4);
        assert.ok(geometry.controls.every(c=>c.x+c.w<=geometry.access.x || c.x>=geometry.access.x+geometry.access.w || c.y+c.h<=geometry.access.y || c.y>=geometry.access.y+geometry.access.h),'Sem sobreposição de controles');
        if(process.env.HOME_BEFORE_MEASUREMENTS) {
          const before=JSON.parse(fs.readFileSync(process.env.HOME_BEFORE_MEASUREMENTS,'utf8')).find(m=>m.width===width&&m.signedIn===signedIn);
          assert.equal(before.brand.y-geometry.brand.y,0,'Posição superior do cabeçalho preservada');
          assert.equal(before.access.y,geometry.access.y,'Posição vertical do acesso preservada');
          assert.equal(before.brand.h,geometry.brand.h,'Altura da marca preservada');
          assert.deepEqual(before.controls,geometry.controls,'Navegação preservada');
          geometry.reducaoSuperior=before.brand.y-geometry.brand.y;
        }
        assert.ok(geometry.access.y >= geometry.brand.y + geometry.brand.h, 'Acesso abaixo da marca');
        assert.ok(geometry.access.w >= 44 && geometry.access.h >= 44);
        const colors=await page.evaluate(()=>({
          resumao:getComputedStyle(document.querySelector('.home-brand-name > span:first-child')).color,
          online:getComputedStyle(document.querySelector('.home-brand-online')).color,
          course:getComputedStyle(document.querySelector('.curso-publico-nome')).color,
          buttonText:getComputedStyle(document.querySelector('.ro-header-access a')).color,
          buttonBackground:getComputedStyle(document.querySelector('.ro-header-access a')).backgroundColor
        }));
        assert.equal(await page.locator('.home-brand-name').textContent(),'ResumãoOnline');
        const wordGap=await page.locator('.home-brand-name').evaluate(e=>{
          const [first,last]=e.children;
          return last.getBoundingClientRect().left-first.getBoundingClientRect().right;
        });
        assert.ok(Math.abs(wordGap)<.1,'Sem espaço, gap ou margem entre as palavras');
        // Verificar os pixels efetivamente renderizados dos SVGs, não só o CSS do img.
        geometry.bookColors=await page.evaluate(async()=>{
          const result={};
          for(const [kind,selector,colors] of [
            ['header','.home-brand-symbol',[[46,125,50],[217,156,0]]],
            ['course','.home-course-icon img',[[23,54,93],[245,185,0]]]
          ]) {
            const img=document.querySelector(selector);await img.decode();
            const canvas=document.createElement('canvas');canvas.width=80;canvas.height=72;
            const ctx=canvas.getContext('2d');ctx.drawImage(img,0,0,80,72);
            const pixels=ctx.getImageData(0,0,80,72).data;
            result[kind]=colors.map(rgb=>{
              let count=0;for(let i=0;i<pixels.length;i+=4)if(pixels[i]===rgb[0]&&pixels[i+1]===rgb[1]&&pixels[i+2]===rgb[2]&&pixels[i+3]===255)count++;
              return {rgb,count};
            });
          }
          return result;
        });
        for(const colors of Object.values(geometry.bookColors))assert.ok(colors.every(c=>c.count>50),'Cores corretas nos pixels renderizados dos livros');
        assert.equal(colors.resumao,'rgb(46, 125, 50)');
        assert.equal(colors.online,'rgb(217, 156, 0)');
        assert.equal(colors.course,'rgb(23, 54, 93)');
        assert.equal(colors.buttonText,'rgb(255, 255, 255)');
        const luminance=values=>values.map(x=>x/255).map(x=>x<=.04045?x/12.92:((x+.055)/1.055)**2.4).reduce((s,x,i)=>s+x*[.2126,.7152,.0722][i],0);
        assert.equal(colors.buttonBackground,'rgb(120, 155, 69)');
        const contrast=1.05/(luminance([120,155,69])+.05);
        assert.ok(contrast>=3,'Contraste do ícone branco (elemento gráfico)');
        const access=page.getByRole('link',{name:'Minha Área',exact:true});
        assert.equal(await access.innerText(),'','Sem texto visível');
        assert.equal(await access.getAttribute('title'),'Minha Área');
        assert.equal(geometry.access.w,width<=600?50:52);
        assert.equal(geometry.access.h,width<=600?50:52);
        const person=await access.locator('svg').boundingBox();
        assert.equal(person.width,24);assert.equal(person.height,24);
        assert.ok(Math.abs(person.x+12-center(geometry.access))<.5);
        assert.ok(Math.abs(person.y+12-geometry.access.y-geometry.access.h/2)<.5);
        for(const [state,color] of [['hover','rgb(112, 143, 64)'],['focus','rgb(112, 143, 64)'],['active','rgb(104, 133, 59)']]) {
          if(state==='hover')await access.hover();
          if(state==='focus'){await page.mouse.move(0,0);await page.keyboard.press('Tab');await access.focus();}
          if(state==='active'){await access.hover();await page.mouse.down();}
          assert.equal(await access.evaluate(e=>getComputedStyle(e).backgroundColor),color,state);
          if(state==='active')await page.mouse.move(0,0),await page.mouse.up();
        }
        await access.evaluate(e=>e.blur());await page.mouse.move(0,0);
        const catalog=await page.locator('.home-cursos-disponiveis-card').evaluate(e=>({svgs:[...e.querySelectorAll('svg')].map(s=>({w:s.getBoundingClientRect().width,h:s.getBoundingClientRect().height})),height:getComputedStyle(e).height,firstGap:e.querySelector('.curso-publico-card').getBoundingClientRect().top-e.querySelector('h2').getBoundingClientRect().bottom}));
        assert.equal(catalog.svgs.length,1);assert.ok(catalog.svgs.every(s=>s.w<=27&&s.h<=27));
        assert.ok(catalog.firstGap>=0&&catalog.firstGap<=16);
        geometry.catalog=catalog;
        geometry.colors=colors;geometry.buttonContrast=contrast;
        assert.equal(await noOverflow(page), true);
        assert.equal(await page.locator('footer').innerText(), `© ${new Date().getFullYear()} Quality`);
        assert.equal(await page.locator('.home-race-track').count(), 0);
        assert.equal(await page.locator('.home-course-arrow').count(), 0);
        assert.equal(await page.getByLabel('Localizar curso',{exact:true}).getAttribute('placeholder'),'Digite o nome completo ou palavra(s)-chave');
        assert.equal(await page.locator('.home-brand-symbol').evaluate(img => img.complete && img.naturalWidth > 0), true);
        assert.equal(await page.locator('h1').innerText(), 'ResumãoOnline\nDIRETO AO PONTO');
        if (artifacts) {
          await page.screenshot({path: path.join(artifacts, `home-${width}-${signedIn?'logado':'publico'}.png`), fullPage: true});
          await page.screenshot({path: path.join(artifacts, `top-${width}-${signedIn?'logado':'publico'}.png`), clip:{x:0,y:0,width,height:Math.min(900,await page.evaluate(()=>document.documentElement.scrollHeight))}});
        }
        await page.getByRole('button', {name: 'Mais cursos', exact: true}).click();
        assert.equal(await page.locator('.curso-publico-card').count(), 6);
        await page.getByRole('button', {name: 'Menos cursos', exact: true}).click();
        assert.equal(await page.locator('.curso-publico-card').count(), 4);
        await page.locator('#buscaCurso').fill('PROFESSOR');
        assert.equal(await page.locator('.curso-publico-card').count(), 2);
        await page.locator('#buscaCurso').fill('sem-resultado');
        assert.equal(await page.locator('#lista-cursos-publicos').innerText(), 'Nenhum curso encontrado.');
        await page.locator('#buscaCurso').fill('');
        const heading = page.locator('.home-cursos-heading');
        assert.equal(await page.locator('.home-cursos-toggle-icon,.home-cursos-toggle').count(),0);
        assert.equal(await heading.getAttribute('role'),null);
        assert.equal(await heading.getAttribute('onclick'),null);
        assert.equal(await heading.getAttribute('tabindex'),null);
        assert.equal(await page.evaluate(()=>typeof alternarCursosDisponiveis),'undefined');
        await heading.click();
        assert.equal(await page.locator('#area_cursos_disponiveis').isVisible(),true,'Lista continua visível ao clicar no título');
        await page.locator('.home-atendimento-header').click();
        assert.equal(await page.locator('#area_atendimento_clean').isVisible(), true);
        assert.equal(await noOverflow(page), true);
        assert.equal(await page.locator('#area_cursos_disponiveis').isVisible(),true);
        assert.deepEqual(errors, []);
        measurements.push({width,signedIn,...geometry,overflow:false,errors});
        await ctx.close();
      }
    }
    // Regressão real: HTML anterior + CSS/JS atuais, antes e após carregar app.js.
    for(const width of [320,390,768,1366]) {
      const ctx=await context(width,null,[courses[0]]);
      const legacy=fs.readFileSync(path.join(root,'index.html'),'utf8')
        .replace('<div class="home-cursos-heading">','<div class="home-cursos-toggle" role="button" tabindex="0" aria-expanded="true" aria-controls="area_cursos_disponiveis" onclick="alternarCursosDisponiveis()" onkeydown="alternarCursosDisponiveis()">')
        .replace(' Cursos disponíveis</h2>',' Cursos disponíveis</h2><svg class="home-cursos-toggle-icon" viewBox="0 0 24 24" fill="none"><path d="m6 9 6 6 6-6" stroke="currentColor" stroke-width="1.7"/></svg>')
        .replace('<div id="area_cursos_disponiveis">','<div id="area_cursos_disponiveis" style="display:none">')
        .replace('</svg>\n      </a>','</svg><span>Minha Área</span>\n      </a>');
      await ctx.route(origin+'/index.html',r=>r.fulfill({contentType:'text/html',body:legacy}));
      let release;const gate=new Promise(r=>release=r);
      await ctx.route('**/js/app.js?*',async r=>{await gate;await r.continue()});
      const page=await ctx.newPage();const loaded=page.goto(origin+'/index.html');
      await page.locator('.home-cursos-toggle-icon').waitFor({state:'attached'});
      try {
        await page.waitForFunction(()=>getComputedStyle(document.querySelector('.home-cursos-toggle-icon')).display==='none');
        assert.equal(await page.locator('.home-cursos-toggle-icon').evaluate(e=>e.getBoundingClientRect().height),0,'Sem seta gigante mesmo antes do JS');
        assert.equal(await page.locator('.home-nav-center a').innerText(),'','Texto legado oculto antes do JS');
      } finally {release();}
      await loaded;await page.locator('.curso-publico-card').waitFor();
      assert.equal(await page.locator('.home-cursos-toggle-icon,.home-cursos-toggle').count(),0);
      assert.equal(await page.locator('.home-nav-center a > span').count(),0);
      const heading=page.locator('.home-cursos-heading');
      for(const attr of ['role','tabindex','aria-expanded','aria-controls','onclick','onkeydown'])assert.equal(await heading.getAttribute(attr),null);
      await heading.click();assert.equal(await page.locator('#area_cursos_disponiveis').isVisible(),true);
      assert.ok((await page.locator('.home-cursos-disponiveis-card').boundingBox()).height<230,'Um curso sem espaço excessivo');
      await ctx.close();
    }
    // Mesma hierarquia da referência quando a API fornecer metadados explícitos.
    for (const width of [320,390,768,1366]) {
      const ctx=await context(width, null, [{id:1,nome:'RESUMÃO PROFESSOR EDUCAÇÃO INFANTIL ALVORADA-RS 2026',orgao:'Alvorada',uf:'RS',ano:2026,cargo:'Professor de Educação Infantil',ativo:true},{id:2,nome:'ZZZ Nome oficial preservado',orgao:'Município confirmado',uf:'SC',ano:2027,cargo:'Professor de Educação Infantil e Atendimento Educacional Especializado em Classes de Ensino Integral',ativo:true}]);
      const page=await ctx.newPage(); await page.goto(origin+'/index.html');await page.locator('.curso-publico-card').first().waitFor();
      assert.equal(await page.locator('.home-course-meta').first().innerText(),'Alvorada/RS • 2026');
      assert.equal(await page.locator('.curso-publico-nome').first().innerText(),'Professor de Educação Infantil');
      assert.equal(await noOverflow(page),true);
      if(artifacts) await page.screenshot({path:path.join(artifacts,`referencia-${width}.png`),fullPage:true});
      await ctx.close();
    }
    // Dados parciais ou ausentes: somente informações explícitas, sem analisar o nome.
    for(const [fields,meta,title] of [
      [{},null,'RESUMÃO PROF EDUC INFANTIL ALVORADA-RS 26'],
      [{orgao:'Alvorada'},'Alvorada','RESUMÃO PROF EDUC INFANTIL ALVORADA-RS 26'],
      [{uf:'RS',ano:2026},'RS • 2026','RESUMÃO PROF EDUC INFANTIL ALVORADA-RS 26'],
      [{cargo:'Professor confirmado'},null,'Professor confirmado'],
      [{orgao:'',uf:null,ano:null,cargo:' '},null,'RESUMÃO PROF EDUC INFANTIL ALVORADA-RS 26']
    ]) {
      const ctx=await context(320,null,[{id:39,nome:'RESUMÃO PROF EDUC INFANTIL ALVORADA-RS 26',ativo:true,publicado:true,...fields}]);
      const page=await ctx.newPage();await page.goto(origin+'/index.html');await page.locator('.curso-publico-card').first().waitFor();
      assert.equal(await page.locator('.curso-publico-nome').innerText(),title);
      assert.equal(await page.locator('.home-course-meta').count(),meta?1:0);
      if(meta)assert.equal(await page.locator('.home-course-meta').innerText(),meta);
      assert.equal(await noOverflow(page),true);await ctx.close();
    }
    // Dados opcionais e conteúdo não confiável: nomes preservados e escapados.
    const special = {id: 8, nome:'Nome oficial <img src=x onerror=alert(1)>', cargo:'Professor <b>teste</b>', orgao:'Órgão & Município', uf:'RS', ano:2026, ativo:true};
    const ctx = await context(320, null, [special]); const page = await ctx.newPage();
    await page.goto(origin + '/index.html'); await page.locator('.curso-publico-card').first().waitFor();
    assert.equal(await page.locator('.curso-publico-nome').innerText(), special.cargo);
    assert.equal(await page.locator('.curso-publico-card').getAttribute('title'), special.nome);
    assert.equal(await page.locator('.home-course-meta').innerText(), 'Órgão & Município/RS • 2026');
    assert.deepEqual(await page.locator('.home-course-content > span').evaluateAll(nodes => nodes.map(n => n.className)), ['home-course-meta', 'curso-publico-nome']);
    assert.equal(await page.locator('.home-course-content img,.home-course-content b').count(), 0);
    assert.equal(await noOverflow(page), true);
    await page.locator('.curso-publico-card').click();
    await page.waitForURL('**/curso-info.html?**');
    assert.equal(new URL(page.url()).searchParams.get('curso_nome'),special.nome);
    assert.equal(new URL(page.url()).searchParams.get('curso_id'),'8');
    await ctx.close();
    // Mesmos destinos e estados de autenticação do acesso central.
    for (const [user, target] of [
      [null, 'login.html'],
      [{is_aluno:true}, 'cursos.html'],
      [{is_admin:true,tipo_admin:'admin_geral'}, 'admin/index.html'],
      [{is_aluno:true,is_admin:true,tipo_admin:'admin_geral'}, 'minha-area.html']
    ]) {
      const ctx = await context(390, user && {id:1,nome:'Teste',ativo:true,...user}); const page = await ctx.newPage();
      await page.goto(origin + '/index.html');
      await page.evaluate(()=>{localStorage.setItem('ultimo_curso_id_compra','1');localStorage.setItem('ultimo_checkout_curso_id','1');});
      await page.getByRole('link',{name:'Minha Área',exact:true}).click();
      await page.waitForURL(origin+'/'+target);
      assert.equal(await page.evaluate(()=>localStorage.getItem('ultimo_curso_id_compra')),null);
      assert.equal(await page.evaluate(()=>localStorage.getItem('ultimo_checkout_curso_id')),null);
      if(!user)assert.equal(await page.evaluate(()=>localStorage.getItem('pos_login_redirect')),'cursos.html');
      await ctx.close();
    }
    // Atendimento mantém os destinos conforme a sessão, e Voltar/Sair seguem operantes.
    for (const signedIn of [false,true]) {
      const ctx=await context(390,signedIn?{id:1,nome:'Teste',ativo:true,is_aluno:true}:null);
      const page=await ctx.newPage();
      for(const [name,target] of [['Atualizar meus dados / ver meu histórico de compras','meus-dados.html'],['Solicitar reembolso','reembolso.html']]) {
        await page.goto(origin+'/index.html?atendimento=aberto');
        await page.locator('#area_atendimento_clean').waitFor();
        assert.equal(new URL(page.url()).searchParams.has('atendimento'),false);
        await page.getByRole('link',{name,exact:true}).click();
        if(signedIn) await page.waitForURL(origin+'/'+target);
        else { await page.waitForURL('**/login.html?next=**'); assert.equal(new URL(page.url()).searchParams.get('next'),target); }
      }
      await page.goto(origin+'/index.html');
      assert.equal(await page.locator('.home-atendimento-btn[href="fale-com-a-clean.html"]').getAttribute('href'),'fale-com-a-clean.html');
      if(signedIn) {
        await page.locator('#btnVoltarHome').click();await page.waitForURL(origin+'/cursos.html');
        assert.equal(await page.evaluate(()=>localStorage.getItem('pagina_antes_inicio')),null);
        await page.goto(origin+'/index.html');
        page.once('dialog',d=>d.accept());await Promise.all([page.waitForNavigation(),page.locator('#btnSairHome').click()]);
        await page.waitForFunction(()=>!localStorage.getItem('access_token'));
        assert.equal(await page.locator('#btnSairHome').isVisible(),false);
      }
      await ctx.close();
    }
    for(const data of [[],[{id:1,nome:'CURSO'+ 'X'.repeat(400),ativo:true}]]) {
      const ctx=await context(320,null,data);const page=await ctx.newPage();await page.goto(origin+'/index.html');
      await page.waitForFunction(()=>document.querySelector('#lista-cursos-publicos').textContent.trim());
      assert.equal(await noOverflow(page),true);await ctx.close();
    }
    const errorCtx=await context(320,null,[],true);const errorPage=await errorCtx.newPage();
    await errorPage.goto(origin+'/index.html');await errorPage.locator('#lista-cursos-publicos h2').filter({hasText:'Erro'}).waitFor();await errorCtx.close();
    const footerFiles = fs.readdirSync(root,{recursive:true}).filter(f=>f.endsWith('.html') && /<footer[\s>][\s\S]*?Quality[\s\S]*?<\/footer>/.test(fs.readFileSync(path.join(root,f),'utf8')));
    const footerCtx=await browser.newContext(); const footerPage=await footerCtx.newPage();
    await footerPage.clock.install({time:new Date('2032-06-15T12:00:00Z')});
    for(const file of footerFiles) {
      const html=fs.readFileSync(path.join(root,file),'utf8');
      const footer=html.match(/<footer\b[^>]*>[\s\S]*?<\/footer>/)[0];
      await footerPage.setContent(footer);
      await footerPage.addScriptTag({path:path.join(root,'js/rodape.js')});
      assert.equal((await footerPage.locator('footer').innerText()).replace(/\s+/g,' ').trim(),'© 2032 Quality',file);
      assert.ok(html.includes('js/rodape.js'),file);
      assert.ok(!/(?:textContent|innerText)\s*=\s*2026\b/.test(html),file);
    }
    assert.equal(footerFiles.length,58);
    await footerCtx.close();
    if(artifacts)fs.writeFileSync(path.join(artifacts,'measurements.json'),JSON.stringify(measurements,null,2));
    console.log('Home: 4 larguras × visitante/logado; alinhamento, overflow, catálogo, pesquisa, lista permanente, atendimento, nomes/metadados, escaping, navegação, autenticação e estados vazio/erro aprovados.');
  } finally {await browser?.close();await new Promise(resolve=>server.close(resolve));}
})().catch(e=>{console.error(e);process.exitCode=1;});
