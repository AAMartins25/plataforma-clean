/* A lista vem exclusivamente do endpoint administrativo autorizado. */
window.GestaoCursos = (() => {
  const campos = ['banca', 'cargo', 'orgao', 'ano', 'uf'];
  const filtros = [...campos, 'produtor_id'];
  const el = id => document.getElementById(id);
  const normalizar = texto => String(texto ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('pt-BR');
  const comparar = (a, b) => a.localeCompare(b, 'pt-BR', {sensitivity:'base'}) || a.localeCompare(b, 'pt-BR');
  let cursos = [], editandoId = null, aoSalvar = null;
  const lista = el('cursoExistenteSelect');
  const form = el('formEditarCurso');
  function mensagem(texto, erro = false) {
    el('msgCurso').textContent = texto;
    el('msgCurso').style.color = erro ? '#8a1f1f' : '#2f5e46';
  }
  function opcoes(select, valores, inicial) {
    select.replaceChildren(new Option(inicial, ''));
    valores.forEach(([valor, texto]) => select.add(new Option(texto, valor)));
  }
  function limpar() {
    filtros.forEach(c => el('filtro-' + c).value = '');
    el('cursoPesquisa').value = '';
    renderizar();
  }
  function renderizar() {
    const selecionado = lista.value;
    const termos = normalizar(el('cursoPesquisa').value).trim().split(/\s+/).filter(Boolean);
    const resultado = cursos.filter(c => filtros.every(chave => {
      const valor = el('filtro-' + chave).value;
      return !valor || String(c[chave] ?? '') === valor;
    }) && termos.every(t => normalizar([c.nome, c.banca, c.cargo, c.orgao, c.ano, c.uf].filter(Boolean).join(' ')).includes(t)))
      .sort((a,b) => comparar(a.nome,b.nome) || a.id-b.id);
    opcoes(lista, resultado.map(c => [String(c.id), c.nome]), resultado.length ? 'Selecione um curso existente' : 'Nenhum curso encontrado');
    if (resultado.some(c => String(c.id) === selecionado)) lista.value = selecionado;
    el('resultadoCursos').textContent = resultado.length ? `${resultado.length} curso(s) encontrado(s).` : 'Nenhum curso encontrado para os filtros e a pesquisa informados.';
  }
  async function carregar(selecionarId) {
    try {
      const resposta = await apiGetAuth('/admin/cursos');
      cursos = (resposta || []).filter(c => c.ativo === true);
      filtros.forEach(chave => {
        const select = el('filtro-' + chave), anterior = select.value;
        const valores = new Map();
        cursos.forEach(c => {
          if (c[chave] != null && c[chave] !== '') valores.set(String(c[chave]), chave === 'produtor_id' ? `${c.produtor_nome || 'Produtor(a)'} (ID ${c.produtor_id})` : String(c[chave]));
        });
        opcoes(select, [...valores].sort((a,b) => comparar(a[1],b[1])), 'Todos');
        if (valores.has(anterior)) select.value = anterior;
      });
      renderizar();
      if (selecionarId != null) {
        if (![...lista.options].some(o => o.value === String(selecionarId))) limpar();
        lista.value = String(selecionarId);
      }
    } catch (erro) {
      cursos = [];
      filtros.forEach(c => opcoes(el('filtro-' + c), [], 'Todos'));
      opcoes(lista, [], 'Erro ao carregar cursos');
      el('resultadoCursos').textContent = 'Não foi possível carregar os cursos. Tente atualizar a lista.';
      throw erro;
    }
  }
  function lerCampos(prefixo) {
    const dados = {};
    for (const chave of campos) {
      const input = el(prefixo + '-' + chave), valor = input.value.trim();
      input.setCustomValidity('');
      if (prefixo === 'novo' && !valor) input.setCustomValidity('Preencha este campo.');
      if (valor && chave === 'ano' && !/^[1-9]\d{3}$/.test(valor)) input.setCustomValidity('Informe um ano de quatro dígitos (1000 a 9999).');
      if (valor && chave === 'uf' && !'AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO'.split(' ').includes(valor)) input.setCustomValidity('Selecione uma UF válida.');
      if (!input.reportValidity()) return null;
      dados[chave] = valor ? (chave === 'ano' ? Number(valor) : valor) : null;
    }
    return dados;
  }
  function editar(id, callback) {
    const curso = cursos.find(c => String(c.id) === String(id));
    if (!curso) { alert('Selecione um curso para editar.'); return; }
    editandoId = curso.id; aoSalvar = callback;
    el('editar-nome').value = curso.nome;
    campos.forEach(c => { el('editar-' + c).value = curso[c] ?? ''; el('editar-' + c).setCustomValidity(''); });
    el('erroEditarCurso').textContent = '';
    form.hidden = false;
    el('editar-nome').focus();
  }
  filtros.forEach(c => el('filtro-' + c).addEventListener('change', renderizar));
  el('cursoPesquisa').addEventListener('input', renderizar);
  el('limparFiltrosCursos').addEventListener('click', limpar);
  el('cancelarEdicaoCurso').addEventListener('click', () => { form.hidden = true; editandoId = null; });
  document.querySelectorAll('.curso-campos input,.curso-campos select').forEach(input => input.addEventListener('input', () => input.setCustomValidity('')));
  form.addEventListener('submit', async evento => {
    evento.preventDefault();
    const dados = lerCampos('editar');
    const nome = el('editar-nome').value.trim();
    if (!dados || !nome || !form.reportValidity() || editandoId == null) return;
    const botao = form.querySelector('[type=submit]');
    botao.disabled = true;
    const id = editandoId;
    try {
      const curso = await apiPutAuth(`/cursos/${id}`, {nome, ...dados});
      if (aoSalvar) aoSalvar(curso);
      form.hidden = true;
      mensagem(`Curso atualizado: ${curso.nome}!`);
      try { await carregar(id); } catch (_) { mensagem('Curso salvo. Não foi possível atualizar a lista; recarregue a página.', true); }
    } catch (erro) {
      el('erroEditarCurso').textContent = 'Erro ao salvar curso: ' + (erro.message || 'Tente novamente.');
    } finally { botao.disabled = false; }
  });
  return {carregar, lerCampos, editar};
})();
