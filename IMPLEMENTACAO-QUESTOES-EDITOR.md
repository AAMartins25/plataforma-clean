# CKEditor 5 nas questões — implementação isolada

Base: `origin/main`, commit `cf3510a`. Worktree: `/tmp/resumao-questoes-editor-20261110` (HEAD destacado). O workspace original permanece na revisão `4ba3ea3`, com suas alterações pendentes preservadas. Não houve commit, push, PR, integração à main ou deploy.

## Resultado

- Enunciado, alternativas editáveis e comentário usam `TeoriaEditor`, com a mesma versão 49.1.0, configuração, plugins, importação Markdown, fórmulas e imagens da teoria. Não foi criada outra configuração do editor.
- Múltipla escolha mantém quatro ou cinco alternativas. Certo/errado mantém as opções fixas C/E e tem editores apenas para enunciado e comentário.
- Cada campo possui identificação de formato. `NULL`/`texto_puro` mantém o legado literal; `html_v1` identifica HTML. A migração não reescreve conteúdos existentes. Clientes que omitem o formato ao editar conservam o formato já gravado.
- O backend reutiliza `preparar_conteudo` da teoria, com sua allowlist, limites, validação de conteúdo vazio, fórmulas e referências de imagens. A leitura adiciona a defesa do DOMPurify antes da renderização.
- Resolução, visualização, resultado, revisão programada, questões críticas, anotações e mensagens exibem o conteúdo conforme seu formato. Fórmulas, imagens e tabelas usam os componentes de leitura da teoria.
- A prévia administrativa distingue o legado de HTML e resume comentários longos como texto, sem cortar tags. A expansão apresenta o conteúdo formatado completo.
- As imagens conservam referências permanentes no conteúdo. As URLs de exibição continuam temporárias. Os vínculos com questões participam da autorização, da duplicação e da manutenção, inclusive da proteção de referências ainda existentes no HTML.
- Cópias de cursos/disciplinas/assuntos preservam formatos e referências de imagens, sem copiar o histórico dos alunos.
- Tipos, gabaritos, limite de dez questões, identidades das alternativas mantidas e bloqueios relacionados ao histórico continuam seguindo as regras existentes.
- As instâncias são encerradas ao remover o formulário. Importações pendentes impedem o salvamento. Se o editor falhar, HTML existente permanece protegido e texto legado pode continuar no modo simples.
- Os estilos de conteúdo rico foram compartilhados com as questões. A barra dos editores se ajusta à largura da página administrativa. Os campos editáveis receberam rótulos acessíveis distintos.

## Principais arquivos

| Camada | Arquivos |
|---|---|
| Formulário | `site-html/js/admin-criar-curso-completo.js`, `site-html/js/editor-questoes.js` |
| Leitura compartilhada | `site-html/js/questao-conteudo.js`, `site-html/js/teoria-imagens.js`, estilos compartilhados e `site-html/css/questao-conteudo.css` |
| Telas | ADM de criação de curso/conteúdo, sprint, teoria, questões críticas, anotações e mensagens |
| Conteúdo/API | `backend/app/questoes_html.py`, `main.py`, `schemas.py`, `models.py`, `aulas.py`, `revisoes.py` |
| Imagens/cópias | `backend/app/imagens.py`, `imagens_manutencao.py`, `copias.py` |
| Esquema | `backend/migrations/025_questoes_html.sql` |

## Validação realizada

| Grupo | Resultado |
|---|---|
| Suíte principal de backend | **396 aprovados**: questões formatadas, segurança, legado, regras, histórico, revisões, cópias, teoria e imagens |
| PostgreSQL descartável | Migração aplicada duas vezes sem alterar o legado; RLS/REVOKE, FKs e cascata aprovados. Os testes existentes de locks e esquema privado das imagens também passaram |
| Persistência em PostgreSQL | Vínculos de imagem, cópia e exclusão da origem preservaram a imagem compartilhada |
| JavaScript administrativo | **12 aprovados** (8 aulas/questões e 4 cópias), além do teste de rotas de revisões |
| Questões no Chromium real | **1366, 768, 390 e 320 px**, sem transbordamento da página: sete editores, certo/errado, salvar/reabrir, gabarito, legado, leitura e revisão |
| Leitura complementar | **9 cenários** dos renderizadores de questões críticas, anotações e mensagens em 1366, 768 e 320 px, com tabela longa, fórmula e imagem |
| Fluxos completos no navegador | Criação de bateria, Markdown, fórmulas, tabelas, upload, reabertura e exibição da imagem; troca de tipos em assunto sem histórico; conclusão automática ao salvar a décima questão; falha de CDN sem sobrescrever HTML |
| Regressão visual da teoria | **32 cenários de tabelas** aprovados; fórmulas e imagens aprovadas em 1280, 768, 390 e 320 px, incluindo ZIP, clipboard, undo/redo, falhas, salvar/reabrir e paginação |
| Revisão estática | `git diff --check` sem erros; nenhum arquivo staged e HEAD permanece na base |

Os testes utilizaram SQLite descartável, Storage sintético e contêineres PostgreSQL próprios. Nenhuma migração foi aplicada a banco real. As fixtures de teste receberam as tabelas necessárias ao código atual de autorização e a função SQLite BTRIM usada nas pontes do navegador.

Logs, JSONs e capturas ficam em `evidencias/questoes-editor/`. Os testes novos estão em `backend/test_questoes_html.py`, `backend/test_questoes_migracao_pg.py`, `site-html/test-editor-questoes.cjs` e `site-html/test-editor-questoes-fluxos.cjs` e `site-html/test-questoes-leitura.cjs`.

## Como testar visualmente

O servidor de demonstração está na porta **8769**:

- Local: <http://127.0.0.1:8769/__preview>
- Codespaces: <https://reimagined-waffle-4jv4jw9pqpwjfqqp4-8769.app.github.dev/__preview>

Se o link do Codespaces não abrir, encaminhe a porta 8769 na aba **Portas/Ports**, mantendo-a privada, e abra `/__preview`.

A página oferece entradas para **ADM**, **Aluno** e **Revisão**, sem informar credenciais reais. Ao alternar o perfil, a sessão sintética é trocada automaticamente.

No ADM:

1. Selecione o curso de teste e clique em **Usar curso selecionado**.
2. Abra **Trabalhar nesta disciplina**.
3. No **Assunto de teste**, abra **Aulas → Questões → Abrir / editar questões**.
4. Edite a questão 1 para conferir todos os campos, fórmula, tabela e imagem. A questão 2 possui quatro alternativas; a questão 3 conserva texto legado com `<b>` literal e quebra de linha.
5. Para criar uma bateria e experimentar mudanças de tipo sem histórico, use o **Assunto livre para criar questões**.
6. Use as entradas de aluno/revisão da página inicial para conferir a exibição da bateria de exemplo.

A prévia usa o banco `/tmp/resumao-questoes-editor-visual/preview.sqlite` e imagens em `/tmp/resumao-questoes-editor-visual/imagens`. Esses dados são sintéticos e persistem em reinícios. A manutenção remota está desativada. O CKEditor da prévia vem da distribuição local da mesma versão, usando GPL exclusivamente no teste, conforme o padrão dos testes existentes. A aplicação normal mantém seu mecanismo de chave comercial.

Para reiniciar o servidor, caso ele não esteja mais em execução:

```bash
cd /tmp/resumao-questoes-editor-20261110
/tmp/resumao-questoes-venv/bin/python backend/preview_questoes_editor.py
```

O script descarta variáveis de ambiente herdadas, bloqueia o carregamento de `.env` pela aplicação e substitui o banco e o armazenamento por recursos locais de teste. Ele serve a interface com a API local; não utiliza o backend de produção.

## Pendências para uma etapa futura

Nenhuma funcionalidade deste escopo ficou pendente. Permanecem sujeitos a nova autorização a integração à main, a aplicação da migração no banco de destino e qualquer publicação. A migração **025** deve ser revisada e aplicada antes de ativar o backend alterado. O arquivo é aditivo, mantém os conteúdos existentes e aplica aos novos vínculos de imagens a mesma proteção privada dos metadados da teoria.
