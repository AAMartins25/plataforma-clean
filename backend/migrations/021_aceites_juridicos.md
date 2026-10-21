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

## Startup e implantação parcial

O startup exclui explicitamente as cinco tabelas jurídicas de `Base.metadata.create_all`; elas são criadas exclusivamente pela migração. As tabelas existentes seguem o comportamento anterior.
Se o backend novo chegar antes da migração, ele verifica a existência de `politica_aceite_juridico`. Enquanto ausente, informa `obrigatorio:false` e mantém o checkout atual. Quando a tabela existe mas não há política habilitada, o resultado também é desativado. Erros inesperados de conexão/SQL não são convertidos em dispensa.
O frontend novo aceita 404 da rota jurídica no backend anterior. Com a política desativada, não exige campo nem altera payload comercial. Assim, frontend e backend podem chegar separadamente mantendo o comportamento anterior. Nunca habilitar a política durante implantação parcial.

A variável `ACEITE_JURIDICO_DISPONIVEL` não é mais usada: a política no banco é a única chave de ativação. Nenhuma variável de produção foi criada ou alterada nesta implementação.

## Ordem recomendada, após autorização

1. Conferir documentos, hashes, campos `[A PREENCHER]` e natureza provisória. Revisar primeiro em homologação.
2. Com backup/procedimento revisados e autorização, aplicar a migração 021. Pode preceder o backend novo; se o backend já estiver atualizado, não terá antecipado as tabelas.
3. Publicar backend manualmente no Render, com política desativada. Confirmar que o endpoint vigente retorna `obrigatorio:false`.
4. Publicar frontend por Auto-Deploy e conferir as duas interfaces, os dois arquivos de `site-html/juridico/`, hashes e cache dos scripts (`juridico.js?v=aceite-2`).
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

Foram executados apenas testes afetados em SQLite efêmero e Chromium com rede interceptada; Mercado Pago simulado. Nenhum SQL de migração foi executado nesta revisão. O teste PostgreSQL da etapa inicial não substitui a validação da migração final em homologação, quando autorizada.
