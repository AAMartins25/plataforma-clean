# Home pública: metadados e quatro ajustes

Base: origin/main `86999549580f3100dbd2444f3674e66abc7138e8`.
Worktree isolada `/tmp/resumao-home-quatro`, branch `home-metadados-publicos`.

## Implementação

1. `GET /cursos-publicos` em `backend/app/main.py` conserva `id`, `nome`, `ativo`, `publicado` e acrescenta somente `cargo`, `orgao`, `uf`, `ano`, diretamente dos campos existentes no modelo. Nenhum schema de banco, migração ou registro de produção foi alterado. Mantidos a consulta SQL, os filtros `ativo == True` e `publicado == True`, a ordenação e o acesso público. O teste exige exatamente essas oito chaves, impedindo exposição de produtor, banca, descrição, dados pessoais ou financeiros. Valores não cadastrados são serializados como null.

O renderizador existente passa a receber os metadados do backend e mantém a ordem órgão/UF • ano, depois cargo. Dados parciais exibem somente conteúdo confirmado; nomes oficiais são o fallback e permanecem nos links. Nenhuma análise de nomes, inferência ou preenchimento de dados. A seta foi removida do HTML dos cartões, e o grid passa a ter só livro e conteúdo. O cartão inteiro continua sendo o mesmo link.

2. Padding superior passa de 14 para 6 px em desktop/tablet e de 10 para 4 px no mobile. Removida também a linha vazia de identificação para visitantes, com redução total de 26 px nas telas maiores e 22 px no mobile. Identificação autenticada mantém sua linha e espaço; controles e slogan preservados. O botão mantém o centro do nome da plataforma.

3. Apenas o título da pesquisa passa para Localizar curso, mantendo a lupa e os estilos.

4. Placeholder nativo passa para Digite o nome completo ou palavra(s)-chave. No mobile, uma cópia visual com aria-hidden e pointer-events:none permite duas linhas legíveis de 14 px, mantendo o input, seu placeholder acessível e o handler original. A cópia desaparece via CSS quando há texto. Em desktop, o placeholder permanece nativo em uma linha. Não houve alteração da lógica de pesquisa.

Marca, slogan, cores, botão, ícone de livros empilhados, Atendimento, SVG do carro e bandeira, rodapé e ano dinâmico mantidos. Sem alterações em CSS global ou páginas administrativas e do aluno.

## Integração real e testes

`backend/test_cursos_publicos.py` carrega a aplicação FastAPI real através do helper de isolamento existente. O módulo de banco configurado é substituído antes da importação por uma fábrica SQLAlchemy em SQLite descartável, sem usar DATABASE_URL ou .env. Não se conecta ao banco de produção. O teste HTTP com TestClient usa a rota real, sem substituir sua função ou seu retorno. Verifica metadados completos, parciais, nulos em cursos antigos, exclusão de cursos inativos/não publicados, contrato legado de `/cursos` e igualdade dos registros antes/depois do GET.

A integração adicional inicia essa mesma aplicação em Uvicorn local. O Chromium carrega os arquivos reais da home e recebe a resposta HTTP real de `/cursos-publicos` daquele servidor, consultando os cursos inseridos somente no SQLite descartável. Não usa JSON fabricado para substituir o endpoint público. O redirecionamento da URL de API no navegador é apenas um proxy para esse endpoint local. O estado de usuário em `/me` é simulado para exercitar o cabeçalho autenticado; não houve login em contas reais.

Duas verificações de contrato/integração aprovadas, incluindo as oito combinações Chromium (320, 390, 768 e 1366 px × visitante/autenticado). Os quatro cursos visíveis incluem Alvorada com os quatro metadados cadastrados no banco de teste, um legado sem metadados, um parcial e um cargo extenso. Três cursos adicionais com publicação/atividade desabilitada não aparecem. Conferidos ausência total de setas, ordem dos textos, fallback, pesquisa por nome oficial completo e palavras-chave, clique no cartão com ID/nome oficial preservados, placeholder completo sem corte e inexistência de overflow.

76 testes existentes de Gestão de Metadados e Cursos Comerciais aprovados. Mais seis suítes frontend aprovadas: compras, Meus Cursos, sessão, autenticação tardia, retorno de pagamento e perfis de acesso. A suíte geral Chromium da home também passou: pesquisa, catálogo, expansão, navegação, acesso por perfis, Atendimento, Voltar/Sair, nomes longos, escaping e rodapés dinâmicos. `node --check` dos scripts e `git diff --check` aprovados.

As oito capturas completas da integração HTTP real foram inspecionadas visualmente. Sem sobreposições, cortes ou transbordamento horizontal. O placeholder é exibido integralmente em duas linhas no mobile, sem reduzir a fonte de entrada de texto. As medições da regressão comparadas à versão anterior confirmam:

| Largura | Estado | Redução superior (px) | Diferença centro botão/nome (px) |
| --- | --- | --- | --- |
| 320 | Visitante | 22 | 0.000 |
| 320 | Autenticado | 6 | 0.000 |
| 390 | Visitante | 22 | 0.000 |
| 390 | Autenticado | 6 | 0.000 |
| 768 | Visitante | 26 | 0.000 |
| 768 | Autenticado | 8 | 0.000 |
| 1366 | Visitante | 26 | 0.000 |
| 1366 | Autenticado | 8 | 0.000 |

`contrato-http-local.json` registra o retorno real da aplicação local, e `medidas-integracao.json` contém a geometria e as verificações do placeholder.

## Limitações e preservação

Não foi realizado deploy no Render nem operação no Supabase. O contrato novo foi validado no backend real executado localmente, com dados de teste descartáveis. A atualização da API em produção dependerá de uma publicação posterior, fora desta tarefa. Não foi consultado o cadastro administrativo ou banco de produção para confirmar se os quatro metadados do curso Alvorada já estão preenchidos. Portanto, as capturas comprovam o resultado quando cadastrados; não afirmam que os registros de produção já contenham esses valores. Se estiverem ausentes, o fallback continuará funcionando.

Nenhum endpoint de pagamento real foi chamado. Autenticação, regras de acesso, checkout e pagamento não foram modificados. Workspace original, suas alterações pendentes e main local preservados. Reutilizados Playwright e Chromium; instaladas somente nh3 e Pillow em /tmp para carregar dependências já exigidas pelo backend, sem alterações de requirements.

## Arquivos de aplicação e testes

- `backend/app/main.py`
- `backend/test_cursos_publicos.py`
- `site-html/index.html`
- `site-html/css/home-publica.css`
- `site-html/js/app.js`
- `site-html/test-home-publica-browser.cjs`
- `site-html/test-home-api-real.cjs`
- Esta pasta de evidências.

## Reprodução local

```sh
PYTHONPATH=/tmp/resumao-home4-python PUBLIC_HOME_BROWSER=1 \
PLAYWRIGHT_MODULE=/tmp/resumao-visual-tools/node_modules/playwright \
CHROMIUM_BIN=/home/codespace/.cache/ms-playwright/chromium-1254/chrome-linux64/chrome \
HOME_REAL_ARTIFACTS=/tmp/resumao-home4-integracao \
python -m pytest -q -s --disable-warnings backend/test_cursos_publicos.py

PYTHONPATH=/tmp/resumao-home4-python python -m pytest -q --disable-warnings \
  backend/test_metadados_cursos.py backend/test_cursos_comerciais.py

PLAYWRIGHT_MODULE=/tmp/resumao-visual-tools/node_modules/playwright \
CHROMIUM_BIN=/home/codespace/.cache/ms-playwright/chromium-1254/chrome-linux64/chrome \
HOME_BEFORE_MEASUREMENTS=auditorias/ajustes-home-20261113/measurements.json \
node site-html/test-home-publica-browser.cjs
```
