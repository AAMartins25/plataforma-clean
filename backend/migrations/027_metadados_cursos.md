# Metadados da gestão de cursos (027)

SQL integral: `027_metadados_cursos.sql`. Execução manual pelo responsável no SQL Editor do Supabase. **Não executado no Supabase por esta implementação.**

**Status informado pelo responsável:** migração executada com sucesso no Supabase de produção; seis colunas nullable, cinco CHECKs e FK conferidos, com NOT VALID intencional. Não reaplicar como parte da integração ou publicação. O roteiro abaixo permanece como referência; a próxima etapa é publicar manualmente backend e depois frontend no Render.

## Esquema inspecionado

- `app/models.py`: `public.cursos` (id integer, nome varchar(255), ativo, publicado, descricao_publica); estrutura própria curso → disciplinas → assuntos → pastas → aulas e conteúdos.
- Identidade: autenticação JWT do próprio backend, resolvida em `usuarios.id`. O produtor referencia essa identidade, não `auth.uid()` do Supabase.
- `app/admin_intermediario.py`, migração 022 e rotas de cursos: Geral e Produção possuem a competência de gestão de todos os cursos; Administrativo e aluno não possuem. Não havia regra de autoria para duplicação ou restrição de cursos por produtor.
- As migrações até 026 não adicionam esses metadados nem autoria aos cursos. A migração 027 é aditiva e verifica o contrato antes de prosseguir. Não altera políticas RLS, grants ou dados históricos.

## Comportamento

- Criação pela API requer nome, banca, cargo, órgão, ano inteiro entre 1000 e 9999 e uma das 27 UFs. Textos são aparados e limitados a 255 caracteres.
- Metadados são nullable no banco: legado não é preenchido automaticamente. Editar somente nome/ativo via clientes antigos preserva metadados omitidos; o formulário completo permite preencher campos antes ausentes. Produtor original não pode ser enviado no POST/PUT.
- Duplicações, inclusive de legados, mantêm metadados disponíveis e registram o duplicador autenticado. Conteúdos, acessos, pagamentos e históricos seguem a rotina existente.
- `/admin/cursos` fornece os metadados apenas após a autorização administrativa existente. `/cursos` mantém a resposta pública anterior, sem metadados ou identidade de produtor. A interface preserva a regra atual de mostrar cursos ativos.
- Filtros são locais sobre o resultado autorizado; não consultam uma lista de usuários. Pesquisa combina palavras parciais no nome e metadados, sem diferenciar caixa ou acentos. Produtores de mesmo nome são distinguidos pelo ID.
- Constraints `NOT VALID` verificam novas escritas sem varrer o acervo; NULL permanece permitido. Não existe NOT NULL, trigger de preenchimento ou atualização histórica.

## Ordem segura de implantação (somente após aprovação)

1. No Supabase correto, conferir o esquema observado e as permissões da conexão usada pelo Render. As consultas abaixo são somente leitura. Não alterar grants/RLS como parte desta migração.
2. Usar uma sessão com permissão de alteração em `public.cursos`, referência em `public.usuarios` e criação de tabelas temporárias no banco. Executar **todo** o SQL 027 no SQL Editor, incluindo BEGIN/COMMIT e consultas finais. Em timeout ou incompatibilidade, interromper, revisar a mensagem e reaplicar somente após resolver; a transação protege o esquema anterior. Não publicar o backend se a transação falhar.
3. Conferir as seis colunas nullable e as seis constraints nas consultas finais; conferir que a contagem de cursos é a mesma registrada antes. `convalidated=false` é esperado: as novas escritas já são verificadas.
4. Publicar no Render o backend e os arquivos estáticos desta mesma revisão. Se forem serviços separados, backend primeiro e frontend logo em seguida, com gravações na gestão de cursos suspensas durante essa janela: o backend novo rejeita criações pelo formulário antigo. As demais áreas não exigem mudança funcional.
5. Abrir a página atualizada e conferir criação, edição de legado, produtor autenticado, duplicação, pesquisa e filtros com Geral/Produção e negativa com Administrativo/aluno. Conferir as larguras indicadas no relatório.

O backend novo depende das colunas já criadas: não inverter os passos 2 e 4. A migração é compatível com o código anterior. Em rollback de aplicação, manter as colunas/dados e suspender novas criações/duplicações até restabelecer a versão que registra metadados e produtor; não executar SQL de remoção.

## Consultas manuais anteriores à migração

```sql
SELECT count(*) AS total_cursos FROM public.cursos;
SELECT table_name, column_name, data_type, character_maximum_length, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name IN ('cursos', 'usuarios')
ORDER BY table_name, ordinal_position;
SELECT tablename, policyname, roles, cmd, qual, with_check
FROM pg_policies WHERE schemaname = 'public' AND tablename IN ('cursos', 'usuarios');
SELECT grantee, table_name, privilege_type
FROM information_schema.table_privileges
WHERE table_schema = 'public' AND table_name IN ('cursos', 'usuarios')
ORDER BY grantee, table_name, privilege_type;
SELECT grantee, table_name, column_name, privilege_type
FROM information_schema.column_privileges
WHERE table_schema = 'public' AND table_name IN ('cursos', 'usuarios')
ORDER BY grantee, table_name, column_name, privilege_type;
```

## Aperfeiçoamento da idempotência

- Antes de adicionar colunas, a migração consulta `pg_index` e verifica uma chave única imediata, válida, pronta, ativa, não parcial e sem expressões, cuja única coluna-chave seja `usuarios.id`. Aceita PK/UNIQUE ou índice único independente, inclusive com colunas INCLUDE. Índices compostos, parciais, inválidos e unicidade adiável não são aceitos. A criação da FK mantém a checagem definitiva do próprio PostgreSQL.
- CHECKs homônimos são conferidos pelo mecanismo nativo de mesclagem de CHECKs na herança do PostgreSQL. Uma tabela temporária vazia copia a estrutura e CHECKs de cursos; uma segunda tabela temporária herda **somente dessa cópia** e declara as expressões esperadas. O PostgreSQL rejeita expressões diferentes, sem comparação de strings e sem substituir CHECKs existentes. `NO INHERIT` nos CHECKs esperados também é rejeitado.
- Essa comparação verifica a compatibilidade estrutural reconhecida pelo PostgreSQL; não prova equivalência lógica de qualquer reescrita algébrica. Uma expressão reescrita de forma não reconhecida pode ser rejeitada por cautela e requer revisão manual.
- As duas tabelas temporárias não contêm dados, não criam FKs/índices, não alteram a herança de `public.cursos` e são removidas automaticamente no COMMIT. Em falha, a transação desfaz a operação. É necessária permissão TEMP no banco. Não há remoção ou substituição automática de restrições permanentes.
- Os timeouts permanecem em 5s para locks e 60s por comando. `search_path` é definido somente na transação, com `pg_catalog` primeiro para resolução determinística dos CHECKs e `public` disponível.

Validação em PostgreSQL 15 e 17.6 descartáveis, sem rede: aplicação inicial, reaplicações na mesma sessão e em sessões novas, dados/vínculos históricos preservados, CHECKs compatíveis com espaços/parênteses diferentes, homônimos incompatíveis, NO INHERIT, tipo errado, FK incompatível, chaves ausentes/inadequadas, índice inválido real e rollback. Também verifica preservação de RLS, grants, view e trigger. Nenhum banco externo utilizado.

Para repetir: iniciar um contêiner novo sem rede, chamado `gestao-cursos-027-refino15` (imagem postgres:15) ou `gestao-cursos-027-refino17` (postgres:17.6), com PostgreSQL acessível localmente pelo usuário postgres no contêiner. Executar, na raiz da worktree:

```sh
TEST_MIGRACAO027_PG=1 TEST_MIGRACAO027_CONTAINER=gestao-cursos-027-refino15 python -m pytest -q backend/test_migracao027_pg.py
```

Cada teste cria e remove seu próprio banco fictício exclusivo. Sem `TEST_MIGRACAO027_PG=1`, a coleta normal ignora esse teste externo. A execução manual no Supabase e o deploy no Render continuam pendentes de aprovação.
