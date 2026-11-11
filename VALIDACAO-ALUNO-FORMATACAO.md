# Validação local: resolução, anotações e mensagens

Checkout isolado: `/tmp/resumao-aluno-formatacao-revisao-20261111`.
Base confirmada diretamente no GitHub: `f0c624183779bedefd1bdd6d6b7bb28c5c3e466b`.
Sem commit, push, PR, deploy ou alteração do workspace original.

## Comportamento

- Na resolução normal, os dois botões de revisão começam esmaecidos e desabilitados.
  Só habilitam após as dez confirmações válidas por `Responder`. Selecionar uma
  alternativa não conta; mudar resposta, dificuldade ou marcação exige confirmar
  novamente. O envio também é bloqueado no handler e o servidor valida o conjunto
  completo, alternativas e dificuldades antes de qualquer gravação.
- Retomada utiliza respostas efetivamente registradas. Revisões programadas mantêm
  o conjunto vigente definido pelo backend, inclusive quando o conteúdo foi alterado;
  não foi criado um limite novo nesse fluxo.
- O editor textual é compartilhado com a infraestrutura de teoria, com negrito,
  itálico, sublinhado, listas, tabelas, alinhamento, links e fórmulas. O perfil do aluno
  não carrega plugins nem controles de inserção de imagens.
- A criação permanece vinculada à questão e tentativa na revisão, conforme o fluxo
  existente. Anotações continuam consultáveis/editáveis na sua área. Mensagens enviadas
  não ganham edição livre: resposta e reformulação conservam suas permissões, turnos,
  limite e confirmação de substituição da conversa.
- Conteúdo antigo continua literal. HTML tem discriminador explícito e sanitização
  no backend e no navegador. Fórmulas e tabelas também aparecem nas listagens, no painel
  do professor e no histórico de cursos expirados.

## Prévia manual

A prévia fica na porta **8772**. No Codespaces, abrir essa porta pela aba **Ports**.
Acessar `/__preview`. Escolher aluno ou administrador utiliza somente dados sintéticos;
nenhum banco, pagamento, e-mail ou armazenamento de produção participa dessa aplicação.

1. Para rever o resultado concluído: `/__preview/entrar?perfil=aluno`.
2. Anotações: `/minhas-anotacoes.html?curso_id=1&contratacao_id=1`.
   Há exemplos ricos e um exemplo de texto legado. Editar, salvar e reabrir.
3. Mensagens: `/mensagens-prof.html?curso_id=1&contratacao_id=1`.
   Conferir a apresentação e, se desejado, reformular usando a confirmação existente.
4. Professor: `/__preview/entrar?perfil=admin`, depois
   `/admin/admin-mensagens-questoes.html`. Ler e responder pelas regras atuais.
5. Para uma nova resolução do mesmo conjunto, entrar novamente como aluno e usar
   no console da prévia a função já existente `renderizarTodasQuestoes()` após
   limpar apenas os estados em memória do navegador:

```js
respostasAluno = {};
dificuldadesAluno = {};
reverQuestoesAluno = {};
respostasConfirmadas.clear();
renderizarTodasQuestoes();
```

Responder nove questões, verificar que os botões continuam bloqueados, selecionar a
décima sem confirmar, e só então clicar em `Responder`. Alterar uma escolha já
confirmada e conferir o novo bloqueio. Testar `Não tenho certeza ou não sei` em
CERTO/ERRADO. O console acima é somente um preparo da prévia local, não uma operação
de produção nem uma exclusão de dados.

Usar as larguras 320, 390, 768 e 1366 px. Confirmar tabelas largas com rolagem local,
fórmulas, barras acessíveis, placeholders e ausência de rolagem horizontal da página.

Se precisar reiniciar a prévia, executar na raiz deste checkout:

```bash
PYTHONPATH=/tmp/resumao-aluno-formatacao-deps PYTHONDONTWRITEBYTECODE=1 /workspaces/resumao-editor-teoria-dev/.local/ckeditor-seguranca-venv/bin/python backend/preview_questoes_editor.py --dados /tmp/resumao-aluno-formatacao-validacao --ckeditor-dist /workspaces/resumao-editor-teoria-dev/.local/ckeditor-seguranca-tools/node_modules/ckeditor5/dist/browser --porta 8772
```

## Testes e evidências

- `evidencias/aluno-formatacao/backend.log`: 94 testes de backend aprovados.
- `backend-final.log`: repetição focalizada da proteção contra cliente antigo.
- `navegador.json` e `navegador.log`: fluxos completos nas quatro larguras,
  incluindo décima resposta, acionamento antecipado, edição posterior,
  salvar/reabrir/editar anotação, enviar/reformular mensagem, fórmulas e tabelas.
- `legado.json` e `legado.log`: retomada, conjunto vigente das revisões,
  texto antigo literal, falha da CDN, XSS de exibição e sete botões Markdown
  e ferramenta de imagens preservados no editor administrativo.
- `botoes-<largura>.png` e `editor-<largura>.png`: capturas das quatro larguras.

Os testes de navegador criam registros sintéticos no banco da prévia. Para repetir
a bateria visual completa, utilizar outro caminho `--dados` vazio; não apagar bancos
existentes. Não é necessário reinstalar Playwright, Chromium ou CKEditor. Somente
Pillow, dependência de teste ausente, foi instalada isoladamente em `/tmp`.

## Limites desta validação

A migração 026 foi preparada, sem execução em produção nem em PostgreSQL nesta etapa.
A prévia usa a distribuição local real de CKEditor e licença de teste GPL; a aplicação
publicada depende da chave comercial já configurada e de disponibilidade da CDN.
Na falta do editor, HTML existente é protegido contra salvamento com perda.
Os históricos expirados foram cobertos por regressão de backend e têm apresentação
compartilhada; os testes visuais completos concentram-se nos fluxos ativos.

## Arquivos alterados e adicionados

- `VALIDACAO-ALUNO-FORMATACAO.md`
- `backend/app/main.py`
- `backend/app/models.py`
- `backend/app/registros_html.py`
- `backend/app/respostas_bateria.py`
- `backend/app/revisoes.py`
- `backend/app/schemas.py`
- `backend/migrations/026_registros_aluno_html.md`
- `backend/migrations/026_registros_aluno_html.sql`
- `backend/preview_questoes_editor.py`
- `backend/test_registros_formatados.py`
- `site-html/admin/admin-mensagens-questoes.html`
- `site-html/css/registro-conteudo.css`
- `site-html/js/editor-teoria.js`
- `site-html/js/registro-conteudo.js`
- `site-html/js/registro-editor.js`
- `site-html/mensagens-prof-expirado.html`
- `site-html/mensagens-prof.html`
- `site-html/minhas-anotacoes-expirado.html`
- `site-html/minhas-anotacoes.html`
- `site-html/sprint.html`
- `site-html/test-registros-aluno.cjs`
- `site-html/test-registros-legado.cjs`

## Situação da migração na integração

A migração 026 foi aplicada e validada manualmente no Supabase de produção pelo
responsável, conforme confirmação recebida antes da integração do código.
Resultado informado: `Success. No rows returned`; estrutura correta nas duas
colunas, com 38 anotações e 29 mensagens, todas em `texto_puro`, sem valores
nulos, inesperados ou `html_v1` nessa verificação. Não houve acesso ao banco
por esta integração e o SQL não foi executado novamente.

A implantação pendente é: backend primeiro, aguardar a atualização completa de
todas as instâncias, depois frontend. A migração incluída no histórico não deve
ser reaplicada nesse banco de produção.
