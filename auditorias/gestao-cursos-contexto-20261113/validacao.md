# Gestão de Cursos — contexto de edição (13/11/2026)

Base: `origin/main` em `c99155da47bc4882cf49c2ccad3ac14b98803bfe`. Trabalho realizado em worktree isolada. Sem mudanças de backend, banco, migrações ou regras de negócio. Nenhum deploy no Render.

## Causa e correção

O módulo GestaoCursos mantinha `editandoId`, callback e formulário abertos mesmo quando a página alterava `cursoAtual`. Criação não limpava as demais seções; seleção limpava apenas parte do estado. Requisições de edição, lista e conteúdo não verificavam se ainda pertenciam ao contexto ativo antes de aplicar resultados ou mensagens.

A troca agora passa por uma rotina de ativação que encerra a edição, apaga ID/callback/campos/validações/erros, limpa disciplinas, assuntos, aulas, baterias e questões, bloqueia e esvazia descrição/valores e invalida continuações antigas. A cópia é ativada explicitamente; exclusão limpa o contexto; recarregamento inicia sem curso ativo. O botão Editar usa o curso ativo, mesmo quando o seletor aponta para outro curso ainda não ativado.

As chamadas de API preservam os argumentos e o destino originais. Respostas de contextos encerrados não chegam às atribuições, mensagens nem às próximas operações. Chamadas já enviadas podem terminar no servidor para seu destino original; a troca não envia salvamentos. Edição e atualização da lista também possuem versões próprias. Funções de bloqueio da configuração foram colocadas dentro do escopo do estado da página, corrigindo referências antes inacessíveis. O CKEditor invalida carregamentos e esvazia seu estado na troca, inclusive durante destruição assíncrona.

`Erro ao salvar curso: Failed to fetch` é gerado pelo catch do PUT de edição em GestaoCursos. Foi reproduzido, com rejeição de rede simulada, seu aparecimento tardio no contexto de outro curso. Esse vazamento foi corrigido; a mesma falha na edição atual permanece visível. Sem rastreamento da requisição original de produção, não é possível atribuir a falha de transporte específica a rede, CORS, disponibilidade do servidor ou outro motivo. Não foi aplicada alteração de infraestrutura nem ocultação genérica de erros.

Foram removidos somente o subtítulo Informações do curso e a mensagem visual sobre metadados antigos. Campos opcionais de cursos legados, CKEditor, formatação e salvamento foram preservados. Versões dos scripts foram atualizadas para evitar mistura de arquivos em cache.

## Validação aprovada

- `node site-html/test-curso-contexto.cjs`: criação com edição A aberta → B; ativação A → B; formulário oculto sem poder salvar; edição explícita vinculada ao ativo; sucesso/erro tardios de edição, inclusive com edição B aberta; atualização tardia da lista; leituras tardias de disciplinas, assuntos, pasta de teoria e configuração; gravações tardias de disciplina e descrição; nenhum salvamento disparado pela troca; erro real de comunicação no contexto atual; legado; cópia; exclusão; reload; filtros; pesquisa; CKEditor real e salvamento formatado.
- `python site-html/test-gestao-cursos-browser.py`: suíte existente de criação, edição, legado, produtor preservado, filtros combinados, pesquisa, ordenação, duplicação, exclusão e erros de lista/edição.
- `node site-html/test-descricao-publica.cjs`: descrição pública, HTML, legado, sanitização, CKEditor real, indisponibilidade do editor, preservação de conteúdo e valores.
- `node site-html/test-duplicar-curso.cjs`: sucesso, erros de duplicação e falha de atualização da lista após cópia.
- Verificações de sintaxe dos três scripts alterados e `git diff --check`.
- Chromium: 320, 390, 768 e 1366 px, sem transbordamento horizontal.

Todas as APIs foram simuladas; nenhum dado real de produção foi alterado. Playwright e Chromium instalados fora do repositório. Testes com CKEditor usaram bundle npm/CSS 49.1.0 local e licença GPL de teste. Para reproduzir os testes JS de navegador, definir `PLAYWRIGHT_MODULE`, `CHROMIUM_EXECUTABLE`, `CKEDITOR_TEST_BUNDLE` e `CKEDITOR_TEST_CSS`. A suíte Python usa a porta CDP 9347 conforme seu cabeçalho.
