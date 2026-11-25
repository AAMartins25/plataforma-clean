(function () {
  'use strict';
  const arquivo = document.getElementById('arquivoImportacao');
  const importarBotao = document.getElementById('importarCurso');
  const status = document.getElementById('statusImportacao');
  let processando = false;
  function mensagemErro(e) {
    if (Array.isArray(e?.detail)) return e.detail.map(item => (item.local || 'arquivo') + ': ' + (item.mensagem || item.msg || 'inválido')).join('\n');
    return e?.message || String(e);
  }
  arquivo.addEventListener('change', () => { status.textContent = ''; });
  importarBotao.addEventListener('click', async () => {
    if (processando) return;
    processando = true;
    importarBotao.disabled = true;
    importarBotao.setAttribute('aria-busy', 'true');
    importarBotao.textContent = 'Importando…';
    arquivo.disabled = true;
    let fase = 'validação';
    let campoNormalizador = null, editorNormalizador = null, editorDescricao = null, campoDescricao = null;
    try {
      const f = arquivo.files[0];
      if (!f) throw Error('Selecione um arquivo JSON ou ZIP.');
      const pacote = /\.zip$/i.test(f.name);
      if (f.size > (pacote ? 64 : 40) * 1024 * 1024) throw Error('O arquivo excede o limite permitido.');
      status.textContent = 'Lendo e convertendo o arquivo…';
      await new Promise(r => setTimeout(r, 0));
      const bytes = await f.arrayBuffer();
      let original, imagens = {};
      if (pacote) {
        const form = new FormData(); form.append('arquivo', f);
        const resposta = await TeoriaImagens.api('/admin/importacoes/cursos/pacote/preparar', form);
        original = resposta.original; imagens = resposta.imagens;
      } else {
        const texto = new TextDecoder('utf-8', {fatal:true}).decode(bytes);
        try { original = JSON.parse(texto); } catch (e) { throw Error('JSON inválido: ' + e.message); }
      }
      const convertido = structuredClone(original);
      const avisos = new Set();
      let disciplinas = 0, assuntos = 0, resumos = 0, baterias = 0, questoes = 0, campos = 0;
      status.textContent = 'Preparando o editor de formatação…';
      campoNormalizador = document.createElement('textarea');
      const area = document.createElement('div');
      area.setAttribute('aria-hidden', 'true');
      area.style.cssText = 'position:fixed;left:-10000px;top:0;width:600px;visibility:hidden';
      area.appendChild(campoNormalizador); document.body.appendChild(area);
      editorNormalizador = await TeoriaEditor.iniciar(campoNormalizador, '', {semImagens:!pacote});
      const C = window.CKEDITOR;
      campoDescricao = document.createElement('textarea'); area.appendChild(campoDescricao);
      editorDescricao = await C.ClassicEditor.create(campoDescricao, {
        licenseKey: window.RESUMAO_CKEDITOR_LICENSE_KEY,
        plugins: [C.Essentials, C.Paragraph, C.Bold, C.Italic, C.Heading, C.List, C.Table, C.TableToolbar, C.FontSize, C.Alignment, C.HorizontalLine],
        toolbar: [], fontSize: {options: Array.from({length:39}, (_,i) => i+10)},
        heading: {options: [
          {model:'paragraph',title:'Parágrafo',class:'ck-heading_paragraph'},
          {model:'heading2',view:'h2',title:'Título 1',class:'ck-heading_heading2'},
          {model:'heading3',view:'h3',title:'Título 2',class:'ck-heading_heading3'},
          {model:'heading4',view:'h4',title:'Título 3',class:'ck-heading_heading4'}
        ]}
      });
      function textoConvertido(obj, chave, caminho, descricao = false) {
        if (typeof obj?.[chave] !== 'string') throw Error(caminho + ': texto obrigatório.');
        try {
          const analise = TeoriaMarkdown.converter(obj[chave], {coletar:true, descricaoPublica:descricao, sublinhado:!descricao});
          if ((!pacote || descricao) && (/!\s*\[|<\s*img\b|&(?:lt|#0*60|#x0*3c);\s*img\b/i.test(obj[chave]) || analise.referencias.length)) throw Error('Imagens não são suportadas neste campo.');
          const resultado = pacote && !descricao ? TeoriaMarkdown.converter(obj[chave], {
            sublinhado:true, resolver: src => imagens[src] ? {src:'/midias/imagens/' + imagens[src]} : null
          }) : analise;
          if (descricao) {
            const modelo = document.createElement('template'); modelo.innerHTML = resultado.html;
            const permitidos = new Set(['P','BR','HR','H2','H3','H4','STRONG','B','EM','I','UL','OL','LI','FIGURE','TABLE','THEAD','TBODY','TFOOT','TR','TH','TD']);
            if ([...modelo.content.querySelectorAll('*')].some(no => !permitidos.has(no.tagName) || (no.tagName === 'FIGURE' && no.className !== 'table')))
              throw Error('A descrição pública não suporta imagens, links, fórmulas ou outros formatos além dos indicados.');
          }
          resultado.avisos.forEach(a => avisos.add(caminho + ': ' + a));
          const editor = descricao ? editorDescricao : editorNormalizador;
          obj[chave] = editor.data.stringify(editor.data.parse(resultado.html));
          if (pacote && !descricao) {
            const contar = html => {const t = document.createElement('template'); t.innerHTML = html; return t.content.querySelectorAll('img').length;};
            if (contar(resultado.html) !== contar(obj[chave])) throw Error('O editor não preservou todas as imagens.');
          }
          campos++;
        } catch (erro) { throw Error(caminho + ': ' + erro.message); }
      }
      if (!convertido?.curso || !Array.isArray(convertido.disciplinas)) throw Error('Informe curso e disciplinas no JSON.');
      textoConvertido(convertido.curso, 'descricao_publica_markdown', 'curso.descricao_publica_markdown', true);
      for (const [di,d] of convertido.disciplinas.entries()) {
        disciplinas++;
        const dp = `disciplinas[${di}]`;
        if (!Array.isArray(d.assuntos)) throw Error(dp + '.assuntos: lista obrigatória.');
        for (const [ai,a] of d.assuntos.entries()) {
          assuntos++; const ap = `${dp}.assuntos[${ai}]`;
          if (!Array.isArray(a.resumos) || !Array.isArray(a.baterias)) throw Error(ap + ': resumos e baterias devem ser listas.');
          for (const [ri,r] of a.resumos.entries()) { resumos++; textoConvertido(r,'texto_markdown',`${ap}.resumos[${ri}].texto_markdown`); }
          for (const [bi,b] of a.baterias.entries()) {
            baterias++; const bp = `${ap}.baterias[${bi}]`;
            if (!Array.isArray(b.questoes)) throw Error(bp + '.questoes: lista obrigatória.');
            for (const [qi,q] of b.questoes.entries()) {
              questoes++; const qp = `${bp}.questoes[${qi}]`;
              textoConvertido(q,'enunciado_markdown',qp+'.enunciado_markdown');
              textoConvertido(q,'comentario_markdown',qp+'.comentario_markdown');
              if (!q.alternativas || Array.isArray(q.alternativas) || typeof q.alternativas !== 'object') throw Error(qp+'.alternativas: objeto obrigatório.');
              for (const letra of Object.keys(q.alternativas)) textoConvertido(q.alternativas,letra,qp+'.alternativas.'+letra);
              if (campos % 100 === 0) await new Promise(r => setTimeout(r, 0));
            }
          }
        }
      }
      status.textContent = 'Verificando os requisitos técnicos no servidor…';
      const hash = [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map(x => x.toString(16).padStart(2,'0')).join('');
      const chaveStorage = 'importacao-curso-v1-' + hash;
      let chave = localStorage.getItem(chaveStorage);
      if (!chave) { chave = crypto.randomUUID(); localStorage.setItem(chaveStorage,chave); }
      let resultado;
      if (pacote) {
        fase = 'importação';
        status.textContent = 'Validando e gravando o pacote…';
        const form = new FormData(); form.append('arquivo', f); form.append('chave', chave);
        form.append('convertido', new Blob([JSON.stringify(convertido)], {type:'application/json'}), 'convertido.json');
        resultado = await TeoriaImagens.api('/admin/importacoes/cursos/pacote/importar', form);
      } else {
        await window.apiPostAuth('/admin/importacoes/cursos/validar', {original, convertido});
        fase = 'importação';
        status.textContent = 'Validação aprovada. Gravando o curso…';
        resultado = await window.apiPostAuth('/admin/importacoes/cursos', {chave, original, convertido});
      }
      status.textContent = `Curso ${resultado.curso_id} ${resultado.repetida ? 'já havia sido importado' : 'importado com sucesso'}. Foi criado sem publicação e com preços provisórios.` + (avisos.size ? '\nAvisos: ' + [...avisos].join(' | ') : '');
      status.style.whiteSpace = 'pre-wrap';
      window.dispatchEvent(new CustomEvent('curso-importado', {detail:resultado}));
    } catch (e) {
      status.textContent = (fase === 'importação' ? 'Falha ao importar: ' : 'Falha na validação: ') + mensagemErro(e) + (fase === 'importação' ? '. Você pode tentar novamente; a chave idempotente será mantida.' : '');
      status.style.whiteSpace = 'pre-wrap';
    } finally {
      try { if (editorDescricao) await editorDescricao.destroy(); } catch (e) { console.warn('Falha ao liberar editor de descrição', e); }
      try { if (campoNormalizador) await TeoriaEditor.destruir(campoNormalizador); } catch (e) { console.warn('Falha ao liberar editor de conteúdo', e); }
      campoNormalizador?.parentElement?.remove();
      arquivo.disabled = false;
      importarBotao.disabled = false;
      importarBotao.removeAttribute('aria-busy');
      importarBotao.textContent = 'Importar curso';
      processando = false;
    }
  });
})();
