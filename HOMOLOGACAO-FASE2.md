# Laboratório local da Fase 2

Preparado na worktree `/tmp/resumao-imagens-fase2`, sem acesso ao Supabase real.
O bucket `teoria-imagens` foi informado pelo administrador como privado, com os
formatos PNG/JPEG/WebP e limite de 5 MB; esta preparação não consulta suas configurações.

## O que está preparado

- PostgreSQL 17.6 Docker `resumao-fase2-homologacao-pg`, com `--network none`, sem
  portas TCP publicadas. A aplicação conecta somente pelo socket Unix privado
  de `/tmp/resumao-fase2-homologacao/pgsocket` ao banco `resumao_imagens_homologacao`.
- Volume nomeado `resumao-fase2-homologacao-pg-dados`, persistente entre reinícios.
  Marcador aleatório confere a identidade do banco e impede adoção acidental de
  outro banco. O preparo não apaga tabelas nem recria dados em reinícios.
- Esquema mínimo por dependências dos modelos dos testes existentes, mais a
  migração 024 aplicada **somente ao PostgreSQL local**. Nenhum SQL no Supabase.
  Administrador, aluno, curso, aula e contratação são fictícios.
- Reutilização do carregador isolado da aplicação e de TestClient. SQLAlchemy usa
  exclusivamente o engine local injetado; `app.database` real e `.env` não são
  carregados. Credenciais/DSN herdados de implantação são descartados. Os JWTs e as
  permissões da aplicação são reais, emitidos com uma chave exclusiva do laboratório.
- TestClient sem lifespan: não inicia serviços financeiros, e-mail ou manutenção.
  O laboratório só expõe materiais/imagens da aula fictícia; não testa os ciclos
  de inicialização de serviços não relacionados à Fase 2.
- Interface em `http://127.0.0.1:8766`, com o CKEditor core oficial 49.1.0 já
  instalado, KaTeX e módulos reais de importação/imagens/paginação da aplicação.
  Chave GPL apenas neste harness local de testes, como nos testes já existentes.
- `API_BASE=location.origin`, CSP `connect-src 'self'`, lista positiva de rotas e
  arquivos estáticos, checagem de Host/Origin e JWTs locais. Não serve `app.js`,
  `teoria.html` completo ou as páginas administrativas que apontam para produção.
  Não existe proxy genérico nem endpoint para URLs fornecidas pelo navegador.
- `IMAGENS_MANUTENCAO_ATIVA=false` e Storage bloqueado por padrão. O backend recusa
  operações de imagem antes de executar o adaptador remoto; a interface exibe
  **Storage BLOQUEADO**. Nenhum upload, assinatura, listagem ou exclusão remoto
  é necessário para iniciar a página nesse modo.

## Comandos locais

Executar da worktree. O launcher reutiliza automaticamente o venv existente e
Pillow temporário, sem instalar dependências nem utilizar configurações de produção.

```bash
cd /tmp/resumao-imagens-fase2
python backend/homologacao_imagens.py preparar
python backend/homologacao_imagens.py iniciar
```

O primeiro comando já foi executado nesta preparação. O segundo mantém o servidor
em primeiro plano e não libera o Storage. Ctrl+C encerra a interface/ponte e preserva
o PostgreSQL/volume. O acesso HTTP é restrito ao Host `127.0.0.1:8766`; encaminhamentos
com outro Host/Origin serão recusados. Para acesso remoto pelo navegador, usar apenas
encaminhamento privado e preparar uma origem exata autorizada antes de abri-lo;
não remover as verificações de origem nem publicar esta porta.

## Configurar as credenciais sem chat nem histórico de shell

No terminal interativo privado do ambiente local, executar:

```bash
python backend/homologacao_imagens.py configurar
```

O programa pede a URL HTTPS do projeto e a chave secreta usando entrada oculta
(`getpass`), valida o formato localmente e grava
`/tmp/resumao-fase2-homologacao/supabase.json` com modo **0600**, em diretório **0700**,
fora da worktree e do Git. Não faz requisição de validação ao Supabase e não libera
o Storage. Não fornecer valores em argumentos de linha de comando, não colar em
chat e não usar `cat`, `printenv`, tracing ou logs para inspecioná-los.

Preferir uma chave `sb_secret_...` exclusiva da homologação, revogável separadamente;
o adaptador também aceita JWT legado `service_role`. Essas chaves têm privilégios
amplos no projeto: a restrição ao bucket é do código, não da credencial.

## Iniciar operações reais — somente após autorização

Depois de configurar a credencial e receber autorização para operações reais,
encerrar a interface bloqueada e iniciar explicitamente:

```bash
python backend/homologacao_imagens.py iniciar --liberar-storage
```

Esse modo não envia arquivos automaticamente ao iniciar: disponibiliza as operações
ao usuário. Ao importar ou colar, o adaptador passa a usar o bucket real, incluindo
eventual exclusão compensatória se um lote falhar. Portanto não executar essa
liberação durante a etapa de preparação. A manutenção continua false em ambos os
modos; não há exclusão periódica ou botão de exclusão na interface.

O navegador passa a permitir imagens somente da origem Supabase configurada, além
da origem local. Todas as APIs continuam locais e as credenciais Supabase ficam
exclusivamente na ponte Python. Referências remotas de Markdown/clipboard continuam
bloqueadas nesta preparação; iniciar com ZIP, arquivos reais no clipboard e seleção
individual de arquivos, preservando texto, tabelas e LaTeX.

Não compartilhar `teoria-imagens` com outro banco nem apagar/recriar o volume após
começar os uploads. Metadados/vínculos persistem no PostgreSQL local. A manutenção
real e seu procedimento de ativação serão homologados separadamente, após autorização.
Antes de usar esse bucket em produção, será necessário planejar seu destino e
preservar/migrar os metadados, ou escolher outro bucket para produção.

## Verificação desta preparação

Somente verificações novas de preparação, sem repetir a suíte aprovada: sintaxe,
permissões dos arquivos privados, inicialização do editor em Chromium e leitura
do PostgreSQL local com JWT fictício. Status confirmou Storage bloqueado e manutenção
false; CSP e lista positiva impediram servir páginas com URLs de produção. Zero
requisições externas durante a verificação. Nenhum upload ou exclusão no Supabase.

Arquivos acrescentados: `backend/homologacao_imagens.py`,
`site-html/homologacao-imagens.cjs` e este documento. Não altera as URLs da plataforma
em produção nem os testes e funcionalidades já aprovados.
