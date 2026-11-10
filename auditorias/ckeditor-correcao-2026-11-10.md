# Validação isolada do CKEditor em Questões

Base: `2825d36f1cf5ae76f8c4b71ed60536413e0ac677`. Alterações sem commit, push, PR, migração ou deploy.

## Correções

- `$$...$$` reconhecido no Markdown e na colagem, com o KaTeX e os widgets já existentes. `\(...\)` e `\[...\]` preservados.
- Fonte recuperada de KaTeX/MathML anotado; fallback para fórmulas explicitamente delimitadas de `text/plain` quando há correspondência completa com os objetos visuais.
- Delimitadores repartidos entre spans/parágrafos são reunidos sem remover a formatação vizinha. Fórmulas já renderizadas são normalizadas sem duplicar wrappers.
- Duas fórmulas em uma linha são tratadas separadamente. Dólar isolado, moeda, código e delimitadores escapados permanecem literais.
- Nenhuma conversão durante carregamento, reabertura, leitura ou salvamento de dados antigos. Fórmulas antigas literais permanecem como estavam; a conversão só ocorre numa nova importação/colagem explícita.
- Atualizados os identificadores de cache dos scripts compartilhados nas páginas que os utilizam.

## Imagens e gráficos

O mecanismo existente passou nos testes de inserção, salvamento, reabertura, assinatura contextual e leitura nos sete campos (enunciado, A–E e comentário). Não houve mudança no armazenamento, na normalização de imagens ou no CSS.

Gráficos PNG/JPEG/WebP de 1000 × 600 foram criados com eixos, título e números; verificaram-se os pixels normalizados, dimensões, proporção e ausência de transbordamento. Inspeção das capturas em smartphone confirmou título, valores e categorias legíveis no exemplo. Isso não garante legibilidade de qualquer gráfico excessivamente denso. Mantidos os limites existentes, inclusive redimensionamento para até 2560 × 2560.

## Testes

- Backend: **103 aprovados**, em SQLite em memória e Storage simulado, incluindo XSS, SSRF, permissões, imagens, gráficos, preservação de histórico e de conteúdo literal.
- `site-html/test-teoria-matematica.cjs`: 1280, 768, 390 e 320 px; conversão, colagem, persistência, reabertura, undo/redo, segurança e paginação.
- `site-html/test-teoria-imagens.cjs`: 1280, 768, 390 e 320 px; ZIP, clipboard, falhas atômicas, imagens, fonte LaTeX, edição e leitura.
- `site-html/test-questoes-matematica-imagens.cjs`: 1366, 390 e 320 px; sete editores reais, importador e evento paste reais, três formatos de gráfico, gravação/reabertura e leitura/comentário do aluno. Inclui conteúdo literal antigo.
- Navegador: Chromium instalado, com viewport móvel emulado; não houve teste em aparelho físico.
- Workspace original: 7.007 hashes de conteúdo inalterados e mesmo estado Git pendente.

## Prévia para conferência

Porta local **8772**, caminho `/__preview`. Encaminhar essa porta no Codespaces com visibilidade privada.

A prévia usa somente dados sintéticos próprios em `/tmp/resumao-ckeditor-correcao-dados` e remove credenciais herdadas antes de carregar a aplicação. A licença `GPL` é usada exclusivamente pelo harness local de teste; o mecanismo de licença de produção não foi alterado.

1. Abra “Resolver bateria como aluno” para ver a questão 1 com fórmulas e gráficos nos campos e use “Revisar agora” para ver o comentário.
2. No Painel ADM: curso de teste → usar curso → disciplina → Aulas → Questões → abrir bateria → editar questão 1.
3. Use “Importar Markdown” com `$$\frac{1}{2}$$`, `\(x^2\)` e `\[a+b\]`. Confira também `R$ 100,00`, `$20` e código cercado por crases.
4. Insira PNG, JPEG ou WebP, salve, reabra e confira como aluno. O formulário possui editores independentes para enunciado, alternativas e comentário.

Copiar visualmente do ChatGPT depende da fonte presente no clipboard. Quando o HTML/texto não contém LaTeX recuperável, use o Markdown; a rotina não tenta reconstruir uma fórmula apenas a partir de sua aparência.

## Reexecução sem instalar dependências

Na raiz da worktree:

```bash
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH=/workspaces/resumao-fase2-preservacao-20261107/dependencias
export PYTHON_TEST_BIN=/workspaces/resumao-editor-teoria-dev/.local/ckeditor-seguranca-venv/bin/python
export PLAYWRIGHT_MODULE=/workspaces/resumao-editor-teoria-dev/.local/ckeditor-seguranca-tools/node_modules/playwright-core
export CKEDITOR_TEST_DIST=/workspaces/resumao-editor-teoria-dev/.local/ckeditor-seguranca-tools/node_modules/ckeditor5/dist/browser
```

No diretório `backend`, usar esse Python com `-m pytest -q -p no:cacheprovider --disable-warnings` nos arquivos `test_questoes_html.py`, `test_teoria_html.py`, `test_teoria_matematica.py`, `test_imagens_teoria.py`, `test_graficos_questoes.py` e `test_ckeditor_permissoes_integracao.py`.

Na raiz, executar os três scripts de navegador acima com `node`. O teste de Questões requer a prévia em execução e as fixtures de `backend/test_graficos_questoes.py` (geradas com o diretório de saída como argumento).

Para iniciar a prévia:

```bash
"$PYTHON_TEST_BIN" backend/preview_questoes_editor.py --dados /tmp/resumao-ckeditor-correcao-dados --ckeditor-dist "$CKEDITOR_TEST_DIST" --porta 8772
```

Capturas locais: `/tmp/resumao-ckeditor-correcao-dados/capturas`. Nenhum arquivo de banco ou captura foi adicionado ao workspace original.

## Preservação das alterações

A worktree está em `/tmp/resumao-ckeditor-correcao`, no volume separado que possui espaço livre. Uma cópia pequena (patch, fontes modificados e manifesto de integridade) foi guardada em `/workspaces/resumao-ckeditor-correcao-preservacao-20261110`, fora do workspace original, para recuperação se o volume temporário for limpo. Essa cópia não contém bancos ou credenciais.
