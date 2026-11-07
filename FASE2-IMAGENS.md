# Fase 2 — imagens e ícones em materiais html_v1

Implementação na branch isolada `fase2-imagens-recuperada-20261107`, worktree
`/workspaces/resumao-imagens-fase2-recuperada`, base
`dbc6feb0a2b16dc4437e4b62d3f325a44c208dfb`. Os 34 arquivos recuperados foram
preservados no commit de segurança `8d9c7f7`. A homologação real de Storage foi
aprovada em 2026-11-07, exclusivamente com PostgreSQL local e dados fictícios.
Não houve push, integração, deploy ou acesso ao banco de produção.

## Uso pelo administrador

1. Preferencial: preparar um ZIP com `conteudo.md` UTF-8 na raiz e imagens em
   `imagens/`. Referenciar as posições assim: `Antes ![Legenda](imagens/figura.png) depois`.
   Não incluir outras pastas, arquivos extras, links simbólicos ou arquivos criptografados.
   Abrir **Importar Markdown**, selecionar o ZIP e clicar em **Importar material**.
2. Alternativa: colar Markdown no importador e selecionar suas imagens de uma vez.
   Os nomes devem corresponder às referências; aceita `figura.png` e `imagens/figura.png`.
   Markdown sem imagens mantém o fluxo anterior, inclusive `\(...\)` e `\[...\]`.
3. Ctrl+V no editor incorpora arquivos de imagem reais, imagens base64 permitidas
   e URLs HTTPS recuperáveis de origens explicitamente autorizadas. Em HTML misto,
   as posições dos elementos `<img>` orientam a inserção. Uma imagem sem HTML
   é inserida na seleção atual. Texto, tabelas e fórmulas acompanham o conteúdo.
4. O botão **Inserir imagens** na barra do editor permite seleção individual ou
   múltipla. Na barra agrupada de telas estreitas, encontra-se no menu de mais opções.
5. Revisar e salvar pelo botão já existente da teoria. Importar não salva o
   material automaticamente; Ctrl+Z desfaz a alteração no editor.

O editor só muda depois de todos os arquivos, conversões e URLs de prévia estarem
prontos. A preparação bloqueia edição/salvamento e permite cancelar o importador.
O limite de 60 segundos encerra a espera também por `File.arrayBuffer()` e outras
promessas não canceláveis. Respostas tardias não alteram o editor nem iniciam novos
uploads. Há verificação de prazo após as etapas síncronas para impedir commit tardio;
como qualquer JavaScript de interface, a liberação depende de o navegador executar
seu event loop (uma aba/processo completamente suspenso não executa timers).
Falha, cancelamento, imagem ausente ou associação ambígua preservam o conteúdo anterior.
O limite total também considera as imagens que já estavam fora da seleção substituída.
Arquivos já transferidos em uma operação cancelada podem ficar pendentes para limpeza;
nenhum material existente é alterado por isso.

## Limitações da colagem

- O ChatGPT e o navegador não garantem arquivos reais no clipboard. Um `<img>`
  pode apontar para um recurso temporário, privado, expirado, `blob:`, `file:` ou
  exigir cookies de uma sessão que o backend não possui. A aplicação não contorna
  autenticação nem utiliza os cookies do ChatGPT.
- URLs remotas exigem HTTPS na porta 443, origem na allowlist, DNS exclusivamente
  público, certificado válido e resposta direta 200. Não há redirects, proxies
  herdados ou transporte de credenciais do navegador. O download usa o IP validado,
  mantendo a verificação TLS do hostname, para impedir troca de destino via DNS.
- Referências inacessíveis sem um File correspondente abortam a colagem inteira
  com mensagem. Vários arquivos sem associação inequívoca às posições exigem ZIP;
  não se presume a ordem dos arquivos do clipboard.
- Fórmulas de HTML KaTeX/MathML precisam da anotação LaTeX recuperável; delimitadores
  literais também são reconhecidos. Fórmulas que vierem somente como pixels são imagens,
  sem fonte editável. Não há OCR. HTML arbitrário e CSS da origem não são preservados.
- Não existe exportador ZIP automático do ChatGPT nesta fase. O pacote deve conter
  arquivos efetivamente baixados/disponíveis; compactar URLs temporárias não os incorpora.
- Ícones Unicode/emoji permanecem texto. Ícones gráficos usam os mesmos formatos
  de imagem, inclusive PNG/WebP transparentes. SVG, GIF, animações, fontes de ícones,
  scripts e HTML disfarçado não são aceitos como upload.

## Armazenamento, segurança e persistência

- Somente PNG, JPEG e WebP estáticos, identificados por decodificação, independentemente
  de extensão/MIME informado. Até 5 MiB por arquivo, 25 MiB por lote/ZIP, 20 imagens
  por teoria, 16 megapixels e 8192 pixels por lado na entrada. Imagens são reduzidas
  proporcionalmente até 2560 pixels por lado, reconstruídas sem metadados e reencodadas.
- ZIP: até 50 entradas e 25 MiB descompactados, razão máxima 200:1, leitura em memória
  sem extrair caminhos. Recusa travessia, caminhos absolutos/ambíguos, nomes duplicados,
  nomes truncados, symlinks, arquivos especiais, formatos extras e ZIP aninhado.
- Limite do corpo HTTP antes do parser multipart, inclusive sem Content-Length;
  HTML continua sanitizado no backend. Apenas administradores da área de produção
  podem importar/assinar prévias. Há limite de 100 imagens pendentes por administrador,
  serializado por lock do usuário em PostgreSQL.
- `html_v1` guarda `/midias/imagens/<uuid>`, nunca uma URL assinada. Esta referência
  lógica não é um endpoint público de bytes. O modelo de dados do CKEditor mantém
  o ID, enquanto a view de edição utiliza uma assinatura temporária.
- O backend usa o JWT/perfil/contexto já existentes. A leitura exige que a imagem
  pertença a um material liberado na aula e contratação/demonstração informada.
  Somente então emite URL de 15 minutos; a interface renova a cada 12 minutos.
  A URL é uma credencial temporária: quem a obtiver poderá usá-la até expirar,
  mesmo após revogação do acesso. Não oferece DRM.
- Cópias de materiais compartilham o arquivo imutável e criam seus próprios vínculos.
  Excluir uma cópia não apaga a imagem das demais. Alterações/exclusões atualizam
  a carência da imagem antes de liberar vínculos.
- A manutenção automática é registrada no ciclo de vida do backend e ativada por
  `IMAGENS_MANUTENCAO_ATIVA=true` (desativada por padrão e nos fixtures). Ao iniciar,
  executa um ciclo e repete a cada cinco minutos. Requer PostgreSQL e as tabelas
  previamente criadas; não executa DDL. Falhas geram aviso sem credenciais e são
  repetidas automaticamente. O shutdown sinaliza parada sem bloquear indefinidamente.
- Pendentes são elegíveis após 24 horas sem vínculo/atividade, em lotes de 100.
  A renovação das prévias mantém rascunhos ainda abertos ativos. A limpeza verifica
  tanto os vínculos quanto referências no HTML de todos os materiais, inclusive
  inativos/cópias, sob lock das linhas. Confirma a remoção dos metadados antes de
  excluir os bytes, impedindo restauração de metadados vinculáveis sem arquivo se
  houver rollback. Falhas de exclusão deixam objetos para reconciliação automática.
- A reconciliação lista o bucket com paginação por nome, até dez páginas de 100
  por ciclo, mantendo o offset entre ciclos e reiniciando ao fim. Só considera
  nomes UUID/extensão criados pela aplicação, datas de criação E atualização válidas
  e anteriores a 24 horas, sem metadados nem referência no HTML. Objetos recentes,
  desconhecidos, com datas ausentes ou referências inconsistentes são preservados.
  O bucket deve ser exclusivo deste banco de aplicação; nunca compartilhar o
  mesmo bucket entre produção, homologação e bancos restaurados independentes.
- Advisory locks em PostgreSQL protegem uploads ainda sem metadados e impedem
  manutenção concorrente por múltiplos workers. Cópias/salvamento disputam os locks
  das linhas. Operações são idempotentes e limitadas; não há transação distribuída
  entre PostgreSQL e Storage. Uma interrupção pode deixar órfãos até o próximo
  ciclo/varredura completa, sem exigir limpeza exclusivamente manual.

## Ativação futura — não executada

1. Revisar e aplicar `backend/migrations/024_imagens_teoria.sql` somente no ambiente
   autorizado. Cria duas tabelas/índices/vínculos e restringe acesso público com RLS.
   Não modifica conteúdos antigos, não cria `html_v2` e não roda automaticamente.
   O usuário SQLAlchemy deve ter acesso às tabelas e bypass adequado de RLS (por
   exemplo, ser seu proprietário); um papel SQL restrito precisará de concessões
   e política específicas revisadas. Não conceder acesso à Data API pública.
2. Manter `teoria-imagens` exclusivamente na homologação e preparar bucket **privado**
   `teoria-imagens-producao` para produção, limite 5 MiB por objeto e MIME types
   `image/png`, `image/jpeg`, `image/webp`. Não criar política pública de download
   ou upload nem expor chave privilegiada ao navegador. A aplicação usa o backend
   com service role; não depende de Supabase Auth no frontend.
3. Definir somente no backend: `SUPABASE_URL` (origem HTTPS do projeto),
   `SUPABASE_SECRET_KEY` (chave atual `sb_secret_...`) ou `SUPABASE_SERVICE_ROLE_KEY`
   (JWT legado `service_role`), e `SUPABASE_IMAGENS_BUCKET=teoria-imagens-producao` em produção
   (`teoria-imagens` somente na homologação).
   A variável SECRET tem precedência. A chave atual viaja somente em `apikey`;
   a legada viaja em `apikey` e `Authorization: Bearer`. Chaves públicas, JWTs anon
   e formatos inválidos falham fechados. Nenhuma chave é enviada ao frontend.
   Manter `IMAGENS_MANUTENCAO_ATIVA=false` na implantação inicial. Qualquer ativação
   futura exige revisão e autorização separadas do bucket e esquema/permissões SQL. Não habilitar sobre bucket compartilhado com outro banco. Disponibilizar
   pelo menos duas conexões SQL simultâneas: uma reserva o lock transacional global
   e outra executa os lotes (o pool existente usa cinco por padrão). Os locks são
   transacionais para compatibilidade com PgBouncer em modo transaction.
   `IMAGENS_HOSTS_PERMITIDOS` é uma lista separada por vírgulas de hostnames exatos
   aprovados para download. Vazia bloqueia referências remotas; ZIP e uploads
   continuam funcionando. Não usar wildcard ou autorizar domínios sem avaliação.
4. Instalar dependências, incluindo `Pillow==13.0.0` (Python >=3.11). Licença
   MIT-CMU incluída em `backend/licenses/Pillow-13.0.0-LICENSE.txt`. Não foi
   acrescentado SDK Supabase nem plugin Premium: usa componentes core Image do
   CKEditor 49.1.0, sob a configuração Cloud Free já existente. A chave GPL é
   utilizada exclusivamente no harness de testes local.
5. Após autorização, homologar num projeto/bucket de teste real: upload, assinatura,
   expiração, indisponibilidade e permissões SQL. O adaptador REST foi testado por
   contrato com respostas simuladas; não houve conexão a Supabase real nesta fase.
   Verificar cotas de armazenamento/tráfego, backup dos objetos e dos metadados,
   retenção e rotina de limpeza. O plano gratuito continua sujeito a suas cotas;
   o código não habilita cobrança nem configura infraestrutura.

## Arquivos

Novos:

- `backend/app/imagens.py`: rotas, limites HTTP, autorização, metadados e vínculos.
- `backend/app/imagens_arquivos.py`: validação/normalização, ZIP e download com proteção SSRF.
- `backend/app/imagens_storage.py`: adaptador REST do bucket privado.
- `backend/app/imagens_manutencao.py`: limpeza/reconciliação, locks e executor periódico.
- `backend/migrations/024_imagens_teoria.sql`: preparação de esquema, sem execução no destino.
- `backend/licenses/Pillow-13.0.0-LICENSE.txt`: licença da dependência.
- `backend/test_imagens_teoria.py`, `backend/test_imagens_schema_pg.py`: testes isolados.
- `backend/test_imagens_manutencao.py`, `backend/test_imagens_locks_pg.py`: correções e concorrência.
- `site-html/js/teoria-imagens.js`: assinaturas e visualização.
- `site-html/js/editor-teoria-imagens.js`: plugin core e preparação atômica do conteúdo.
- `site-html/css/teoria-imagens.css`: responsividade/status, com seletores restritos.
- `site-html/test-teoria-imagens.cjs`: integração de navegador/editor/backend simulado.
- `site-html/test-imagens-timeout.cjs`: prazos/cancelamento com relógio virtual, sem rede.
- `FASE2-IMAGENS.md`: procedimento, ativação e evidências desta fase.

Modificados:

- `backend/app/models.py`, `backend/app/database.py`: metadados e exclusão do create_all automático.
- `backend/app/main.py`, `backend/app/copias.py`: salvar/editar/copiar vínculos e registrar rotas.
- `backend/app/teoria_html.py`: imagens próprias na allowlist; recusa imagens não incorporadas.
- `backend/requirements.txt`: Pillow.
- `backend/test_teoria_html.py`: remove imagem externa do caso genérico de sanitização;
  a recusa explícita de referências externas passa a ser testada na suíte de imagens.
- `site-html/js/editor-teoria.js`, `site-html/js/editor-teoria-markdown.js`: plugin, importador e guardas.
- `site-html/js/admin.js`, `site-html/js/admin-criar-curso-completo.js`: impedir salvar enquanto prepara.
- `site-html/admin/aula-conteudo.html`, `site-html/admin/criar-curso-completo.html`: carregar módulos/CSS.
- `site-html/teoria.html`: referências na leitura e paginação ponderada por imagem.
- `site-html/test-teoria-matematica.cjs`: carregar dependências novas e adequar o harness ao importador.

Os botões laterais Texto/Vídeo/Questões não foram alterados.

## Validação local

- Backend: 47 casos de imagens/segurança, 20 HTML/LaTeX e 193 aulas/cópias aprovados.
  Usam FastAPI real com SQLite descartável e Storage em memória. Não carregam o
  banco configurado. TestClient executado isoladamente, fora da restrição de IPC
  do sandbox identificada na Fase 1, sempre com timeout externo.
- PostgreSQL 17.6: 1 teste em contêiner descartável `--network none`, sem publicação
  de portas, validando execução/idempotência do SQL, RLS/permissões, constraints e
  cascata dos vínculos sem apagar objetos compartilháveis. Contêiner removido ao fim.
- Chromium/CKEditor oficial 49.1.0: ZIP, posições, File e HTML misto, URLs simuladas,
  LaTeX, falha parcial, salvar/reabrir/editar, desfazer/refazer, visualização do aluno,
  paginação e ausência de overflow em 1280/768/390/320 pixels. Regressão de fórmulas
  da Fase 1 nas mesmas quatro larguras. Não houve uso de conta ChatGPT/Supabase real.
- O harness usa CSP para bloquear conexões/imagens externas. Arquivos são colados
  pelo clipboard nativo do Chromium e Ctrl+V: eventos sintéticos com DataTransfer
  apresentaram leitura intermitente de Blob durante a construção do teste. A
  aplicação materializa os arquivos durante o evento e aplica timeout à operação;
  falhas expiram e preservam o conteúdo anterior.
- Capturas fora da worktree em `/tmp/resumao-imagens-evidencias/` e
  `/tmp/resumao-fase2-formulas-evidencias/`. Checagens de sintaxe e `git diff --check`.

Reexecução (ambiente de testes com dependências instaladas):

```bash
cd backend
timeout 90s python -m pytest -q -p no:cacheprovider test_imagens_teoria.py test_teoria_html.py test_teoria_matematica.py test_aulas_admin.py test_copiar_conteudo.py
IMAGENS_TESTAR_POSTGRES=1 timeout 90s python -m pytest -q -p no:cacheprovider test_imagens_schema_pg.py
```

Os testes de navegador exigem `PLAYWRIGHT_MODULE`, `CKEDITOR_TEST_DIST` apontando
para o dist/browser oficial 49.1.0 e `PYTHON_TEST_BIN` para o ambiente de testes:

```bash
timeout 130s node site-html/test-teoria-imagens.cjs
timeout 100s node site-html/test-teoria-matematica.cjs
```

Limites da validação: emulação de larguras em Chromium, sem ensaio em dispositivos
físicos/Safari/Firefox e sem clipboard real da sessão ChatGPT. Integração ao Supabase
real e ativação ficam pendentes de autorização.

## Correções após a revisão final

Validação adicional restrita às pendências, sem repetir toda a suíte:

- 18 casos novos de manutenção/chaves: ambas as gerações de chave e cabeçalhos
  em upload/assinatura/listagem/exclusão, rejeição de chaves públicas/inválidas,
  carência, referências em vínculos e HTML, falha SQL sem perda de objetos, falha
  remota com retry, paginação, cota de 100 pendentes, heartbeat e executor periódico.
- 1 teste novo em PostgreSQL Docker sem rede/portas verifica locks de uploads
  contra reconciliador e exclusão mútua entre workers. Não executa migrations.
- 6 casos preexistentes diretamente afetados foram selecionados: contrato Storage,
  upload/gravação/acesso, cópia/carência, compensação parcial, restrição de autor
  e bloqueio de acesso não autenticado.
- 7 casos JavaScript de timeout/cancelamento/resultado tardio/API abortada com
  relógio virtual. O cenário novo de navegador usa o mesmo CKEditor 49.1.0 e
  verifica a recuperação em tela de 320px, seguida de ZIP, Ctrl+V, gravação e
  reabertura preservando imagens, tabela e LaTeX.

```bash
node site-html/test-imagens-timeout.cjs
cd backend
timeout 90s python -m pytest -q -p no:cacheprovider test_imagens_manutencao.py
IMAGENS_TESTAR_LOCKS_PG=1 timeout 90s python -m pytest -q -p no:cacheprovider test_imagens_locks_pg.py
```

No comando de navegador já descrito, usar `IMAGE_TEST_CORRECOES=1 IMAGE_TEST_WIDTHS=320`
para executar somente a verificação nova, sem repetir os cenários aprovados.

Referências oficiais verificadas para o contrato do adaptador:
[chaves e cabeçalhos](https://supabase.com/docs/guides/getting-started/api-keys) e
[paginação de objetos](https://supabase.com/docs/reference/python/storage-from-list).
Nenhuma conexão ao Supabase real foi feita; continuam pendentes os ensaios de
permissões, timestamps/listagem e expiração no projeto exclusivo de homologação.


## Consolidação após homologação real — 2026-11-07

As evidências históricas acima descrevem suas respectivas etapas. A integração
real posterior confirmou quatro objetos fictícios PNG/JPEG/WebP, ZIP, Ctrl+V
nativo, inserção individual, persistência/reabertura exata, leitura como aluno e
recusa de acesso indevido. Após o prazo natural de 900 segundos, a assinatura
antiga foi recusada; a API local renovou a assinatura e os bytes mantiveram o SHA-256.
A renovação periódica da interface foi acionada com relógio do navegador controlado,
usando assinaturas reais no backend. Nenhum objeto foi excluído.

Os ajustes de caminhos persistentes, inicialização dos codecs antes do carregador
isolado e bloqueio de exclusões pertencem às ferramentas locais de homologação.
Não modificam o adaptador funcional da aplicação. As credenciais, o estado privado,
os arquivos fictícios e os relatórios detalhados permanecem fora do Git.
A manutenção automática permanece desativada. A consolidação não integra a main;
a main local contém trabalho não commitado que deve ser preservado.

## Preparação final: transações e ambientes

O uploader preserva os objetos se houver qualquer falha após iniciar o commit,
mesmo que um rollback local posterior retorne sem erro. Antes do commit, somente
compensa uploads confirmados quando a conexão continua válida e o rollback termina
com sucesso. Falha de rollback ou conexão perdida também preserva os objetos.
Órfãos devem ser reconciliados posteriormente por procedimento autorizado;
a manutenção automática continua desativada.

Os perfis sem credenciais em `preparacao/fase2/` selecionam buckets diferentes
no mesmo projeto. Banco, chave da aplicação, credenciais do backend e metadados
são próprios de cada ambiente. Os quatro objetos fictícios e seus vínculos ficam
na homologação; não copiar esses registros para produção. Chaves privilegiadas
Supabase têm escopo amplo: o isolamento por bucket depende da configuração correta
do backend; não constitui isolamento de privilégios da credencial no projeto.

Validação final direcionada: 10 casos aprovados com SQLite descartável e Storage
em memória: rollback comprovado, commit sem confirmação antes/depois da persistência,
rollback falho, conexão invalidada/fechada, dois perfis de bucket e regressões de
compensação parcial e salvar/reabrir/acesso autorizado. Sem rede ou credenciais.
