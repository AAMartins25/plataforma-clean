# Migração 021 e implantação controlada — revisão final

Somente preparação. Não executar migração, INSERTs, integração, publicação ou ativação sem autorização.

## Estado e estrutura

Os PDFs 1.0 foram recebidos na pasta definitiva `site-html/juridico/`. Na worktree isolada, essa pasta contém cópias idênticas aos originais. Os links nas páginas de compra abrem esses PDFs no frontend. O backend conserva cópias arquivadas em `backend/documentos_juridicos/1.0/`, com textos integrais e manifesto de hashes, para integridade e recuperação histórica. Nunca substituir o conteúdo de arquivos já aceitos; atualizações exigem nova versão e novo nome de arquivo.

A migração cria cinco tabelas novas:
- `documentos_juridicos_versoes`: texto e hash, hash opcional do PDF, tipo/versão únicos e publicação UTC.
- `politica_aceite_juridico`: registro único, inicialmente desabilitado, com referências ao par vigente.
- `aceites_juridicos`: aluno, curso, prazo, oportunidade, meses, modalidade, valores, declaração e data/hora UTC do servidor.
- `aceites_juridicos_documentos`: versões exatas associadas a cada evento.
- `aceites_juridicos_pagamentos`: vínculo com a intenção de pagamento local. Para transações derivadas, consultar o pagamento de origem.

SQL transacional, sem UPDATE/DELETE/INSERT em pagamentos ou contratos anteriores. Não há backfill, FK nova nas tabelas históricas nem exclusão em cascata. O hash do texto é validado no PostgreSQL. Quatro triggers rejeitam UPDATE/DELETE nas versões, eventos e vínculos.
`lock_timeout=5s` e `statement_timeout=60s` limitam bloqueios/duração; a criação de FKs pode precisar de locks breves nas tabelas referenciadas. Se houver falha, abortar/reverter toda a transação, sem insistir em horário de carga. A migração é de execução única: se estruturas já existirem, conferir o esquema antes de tentar novamente.

## Isolamento da Data API — proteção antes do COMMIT

A execução exige `current_user=postgres`, schema `public`, `sha256(bytea)` nativa e
as roles Supabase `anon`, `authenticated` e `service_role`. Não há `SET ROLE`
automático. Uma identidade ou dependência incompatível aborta a transação.

As cinco tabelas, três sequências SERIAL e a função de imutabilidade recebem
REVOKE ALL de PUBLIC e das três roles da API. Somente esses objetos são afetados;
não há ALTER DEFAULT PRIVILEGES, REVOKE global ou alteração de ACL das tabelas
históricas. Os objetos jurídicos continuam pertencendo a postgres.

RLS é habilitada nas cinco tabelas, sem políticas e sem FORCE RLS. O proprietário
postgres continua consultando e gravando pelo FastAPI. A role service_role pode
ter BYPASSRLS: seu isolamento depende também do REVOKE, não apenas de RLS.
RLS não substitui REVOKE para operações como TRUNCATE.

Antes do COMMIT, a migração verifica proprietário, ACL de PUBLIC, permissões
efetivas de tabelas/colunas/sequências/função, associações transitivas das roles
da API (incluindo NOINHERIT), configuração RLS sem políticas e acesso do backend.
Se grants herdados continuarem permitindo acesso, a migração falha e reverte
integralmente. Não tenta alterar associações ou privilégios de outras estruturas.
A política deve terminar desabilitada e sem documentos selecionados.

Requisitos operacionais: executar o arquivo completo com interrupção no primeiro
erro (`psql -X -v ON_ERROR_STOP=1 -f ...`), sem envolver em outra transação externa,
pois o arquivo já contém BEGIN/COMMIT. Em caso de erro, confirmar ROLLBACK/encerrar
a conexão dedicada e conferir os objetos antes de qualquer repetição. Não executar
fragmentos nem habilitar a política durante a implantação. O executor deve poder
revogar os grants preexistentes dos objetos novos; se não puder, a verificação
final deve impedir o COMMIT. Conferir privilégios efetivos novamente após migração,
importação e deploy, inclusive eventual automação de grants do projeto Supabase.

## Testes PostgreSQL de segurança (opt-in, somente local)

`backend/test_migracao021_seguranca_pg.py` exige um cluster descartável acessível
por loopback. Nunca utiliza a DATABASE_URL de produção como destino. Cada teste
cria e remove um banco de nome aleatório com proprietário postgres.

Preparação do cluster de testes (não executar no Supabase): inicializar a imagem
postgres:17.6 com POSTGRES_USER=auditor_021, uma senha exclusivamente local e um
banco administrativo de testes. Como esse administrador local, criar:

- postgres com LOGIN, NOSUPERUSER e NOBYPASSRLS, com senha apenas de testes;
- anon e authenticated com NOLOGIN;
- service_role com NOLOGIN e BYPASSRLS;
- api_021_grupo com NOLOGIN; conceder essa role a authenticated.

Fornecer JURIDICO_021_TEST_ADMIN_URL apontando para esse administrador local e
JURIDICO_021_TEST_POSTGRES_PASSWORD com a senha local de postgres. Executar:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -B -m pytest -p no:cacheprovider backend/test_migracao021_seguranca_pg.py -q
```

Os testes concedem defaults amplos a PUBLIC e às roles da API apenas nos bancos
criados para o ensaio. Incluem um cenário de grant herdado que deve abortar, role
executora incorreta, política RLS indevida, rollback integral e execução duplicada.
O teste do backend roda como postgres sem SUPERUSER/BYPASSRLS, importa os documentos
reais e confere os hashes. Compras, renovação e reutilização usam Mercado Pago
simulado; aceite é ativado e desativado somente nesse banco descartável. As roles
clientes não conseguem ler as cinco tabelas nem usar as três sequências e não têm
EXECUTE na função. Um grant SELECT temporário demonstra o bloqueio adicional por
RLS; ele é revertido na própria transação. A ACL de uma tabela histórica permanece
idêntica. Sem a variável de opt-in, esses testes são ignorados.

## Startup e implantação parcial

O startup exclui explicitamente as cinco tabelas jurídicas de `Base.metadata.create_all`; elas são criadas exclusivamente pela migração. As tabelas existentes seguem o comportamento anterior.
Se o backend novo chegar antes da migração, ele verifica a existência de `politica_aceite_juridico`. Enquanto ausente, informa `obrigatorio:false` e mantém o checkout atual. Quando a tabela existe mas não há política habilitada, o resultado também é desativado. Erros inesperados de conexão/SQL não são convertidos em dispensa.
O frontend novo aceita 404 da rota jurídica no backend anterior. Com a política desativada, não exige campo nem altera payload comercial. Assim, frontend e backend podem chegar separadamente mantendo o comportamento anterior. Nunca habilitar a política durante implantação parcial.

A variável `ACEITE_JURIDICO_DISPONIVEL` não é mais usada: a política no banco é a única chave de ativação. Nenhuma variável de produção foi criada ou alterada nesta implementação.

## Ordem recomendada, após autorização

1. Conferir documentos, hashes, campos `[A PREENCHER]` e natureza provisória. Revisar primeiro em homologação.
2. Com backup/procedimento revisados e autorização, aplicar a migração 021. Pode preceder o backend novo; se o backend já estiver atualizado, não terá antecipado as tabelas.
3. Publicar backend manualmente no Render, com política desativada. Confirmar que o endpoint vigente retorna `obrigatorio:false`.
4. Publicar frontend por Auto-Deploy e conferir as duas interfaces, os dois arquivos de `site-html/juridico/`, hashes e cache dos scripts (`juridico.js?v=aceite-3`).
5. Revisar e executar, somente no ambiente autorizado, os dois INSERTs de `backend/documentos_juridicos/1.0/documentos-1.0.sql`. Não habilitam a exigência.
6. Verificar estrutura, triggers, conteúdo, cópias de PDFs e hashes. Confirmar implantação completa do frontend/backend e existência de um único documento de cada tipo/versão. Os textos 1.0 continuam provisórios, com os campos não preenchidos.
7. Somente mediante nova autorização, selecionar e habilitar o par na transação abaixo. Nenhum novo deploy ou mudança de variável é necessário:

```sql
BEGIN;
UPDATE politica_aceite_juridico SET
  termos_id = (SELECT id FROM documentos_juridicos_versoes WHERE tipo='TERMOS' AND versao='1.0'),
  privacidade_id = (SELECT id FROM documentos_juridicos_versoes WHERE tipo='PRIVACIDADE' AND versao='1.0'),
  habilitada = TRUE
WHERE id=1;
COMMIT;
```

8. Verificar a rejeição de POST sem aceite sem criar uma preferência válida em produção. Testes de criação/reabertura válidas devem usar homologação/mocks, sem operações financeiras reais.

O cliente consulta novamente a política antes de iniciar a compra: uma página aberta com a exigência desativada reconhece ativação posterior e pede confirmação. Mudança de versões limpa a marcação. A validação backend continua soberana; páginas antigas podem precisar de atualização após a ativação.

## Histórico e recuperação

O registro do aceite não é aprovação do pagamento. O evento é registrado antes da chamada ao MP e participa da transação já usada pelo checkout local, sem alterar a ordem de commits do fluxo financeiro. A reabertura registra novo evento vinculado à mesma preferência, preservando os anteriores.
Confirmação, webhook, revalidação e concessão de acesso não exigem aceite retroativo. Preferências emitidas anteriormente continuam processáveis. Renovações futuras conservam os aceites anteriores. Demonstrações e concessões administrativas permanecem independentes.
O texto pode ser recuperado por ID em `/public/juridico/documentos/{id}`; há também o PDF arquivado por hash em `/public/juridico/arquivos/{sha256}.pdf`. O manifesto associa tipo/versão e hashes do texto/PDF; o backend verifica integridade antes de iniciar/reabrir checkout. Os links do aluno usam `pdf_site_url` da versão, relativo à mesma base do frontend, sem URL fixa de produção.

Se houver necessidade operacional de suspender a exigência, uma decisão autorizada pode alterar somente `habilitada=FALSE`, sem deploy. Não apagar evidências, alterar pagamentos ou reverter contratos. Reverter apenas o frontend com a política ativa pode impedir novas compras; desabilitar a política antes de tal rollback.

## Verificação desta revisão

A migração com REVOKE/RLS foi executada integralmente em PostgreSQL 17.6 local e descartável, com defaults amplos. Os cinco testes PostgreSQL de segurança passaram, incluindo o backend como proprietário sem SUPERUSER/BYPASSRLS. A regressão jurídica/financeira foi validada: 113 testes passaram inicialmente; a única falha era a ausência dos PDFs na cópia temporária. Após incluir os PDFs versionados, esse teste também passou (114 casos aprovados). Nenhuma migração ou alteração foi realizada em produção. Esquema real, permissões do executor e backup recuperável de produção continuam sujeitos à confirmação antes da implantação.
