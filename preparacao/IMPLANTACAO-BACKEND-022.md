> Documento histórico do intermediário 022. Para os três perfis definitivos, consulte [PUBLICACAO-PERFIS-DEFINITIVOS.md](PUBLICACAO-PERFIS-DEFINITIVOS.md). Não executar as instruções de migração deste roteiro nesta preparação.

# Backend intermediário sobre o frontend publicado

Preparação local. Base direta: 702b9e5bfba3d142d4c740e2091e0f0f8e1d79e2.
Referência funcional: c50b207448f69429ff02a580ef7531a6effcf4f2.
O novo commit backend preserva todos os arquivos do commit de referência byte a byte; somente este documento é adicional. Nenhuma alteração em site-html em relação ao frontend publicado. Relatórios anteriores são registros históricos; este roteiro substitui a proposta anterior de integrar frontend e backend em dois commits a partir da base antiga.

## Pré-condições e autorização futura

Não executar os comandos seguintes nesta preparação. Exigem autorização explícita para backup, restauração isolada, push, manutenção, migração e deploy, conforme a operação. Não usar cdba603 nem o commit exclusivo frontend como recuperação backend após a 022. Registrar o SHA completo do novo commit seguro antes de publicar. O serviço backend continua manual; um push poderá redeployar o frontend, cujos bytes são os mesmos publicados.

Confirmar no Render: SHA Live, Auto-Deploy Off do backend, ausência de deploy pendente, comandos de build/start/pre-deploy, Python/dependências e disponibilidade de seleção do SHA seguro. Confirmar que nenhum pre-deploy aplica migrações. Revalidar main remota antes de qualquer push; não forçar nem transportar o workspace principal.

## Backup restaurável

Usar pg_dump/pg_restore/psql versão 17, máquina autorizada e conexão administrativa protegida. Os nomes de serviço abaixo são exemplos: precisam ser previamente configurados/validados por operador autorizado fora do repositório, com passfile protegido, sem divulgar URL/senha. Não são novas credenciais nem alteração de DATABASE_URL. Se perfis protegidos não existirem, parar e definir o canal seguro antes de executar. Preferir conexão direta para backup; Session Pooler exige validação específica. Não usar Transaction Pooler.

Backup inicial e ensaio de restauração devem ocorrer antes da janela. Backup final após drenar todos os escritores, antes da 022. Caminhos de saída protegidos fora do Git, armazenamento criptografado e acesso restrito; a massa contém dados pessoais e hashes de senha. Definir cobertura de schemas, extensões, ownership/ACLs e papéis gerenciados Supabase. pg_dump não inclui papéis globais nem objetos físicos do Storage. Não executar restauração destrutiva no projeto de produção.

Exemplos para execução futura em shell autorizado (substituir nomes/caminhos após revisão):

```bash
pg_dump --version
pg_restore --version
psql --version
# /CAMINHO_PROTEGIDO deve existir com acesso restrito; não publicar o dump.
pg_dump --dbname='service=resumao_admin' --format=custom --file=/CAMINHO_PROTEGIDO/pre022.dump
# Prosseguir somente se exit code zero e avisos revisados.
sha256sum /CAMINHO_PROTEGIDO/pre022.dump
pg_restore --list /CAMINHO_PROTEGIDO/pre022.dump
# Destino deve ser novo, vazio, isolado e comprovadamente diferente de produção.
# Preparar extensões/papéis exigidos conforme plano de restauração Supabase.
pg_restore --dbname='service=resumao_restore_isolado' --exit-on-error --single-transaction /CAMINHO_PROTEGIDO/pre022.dump
```

Não adicionar --clean nem ignorar erros de ownership/ACL. Adequações de restauração devem ser aprovadas e preservar as permissões relevantes. Listagem/checksum não provam restauração: verificar schema, constraints, FKs, sequências, valores/vínculos dos usuários, vendedores, pagamentos e acessos e funcionamento da aplicação com efeitos externos bloqueados. Backup final deve ser conferido e vinculado ao ensaio bem-sucedido; prazo e perda de dados aceitável precisam estar definidos.

## Manutenção e drenagem

Disponibilizar previamente, mediante autorização de push, o SHA seguro completo. No Render, a partir desse mesmo SHA, o comando temporário previsto para Root Directory backend é:

```text
python -u manutencao_temporaria.py
```

Não iniciar app.main antes de confirmar a 022. Manutenção retorna GET / e /__maintenance_health com status maintenance; outras operações 503, incluindo webhooks. O deploy temporário também pode sobrepor processos: aguardar encerramento dos Uvicorn anteriores e operações em andamento, verificar instâncias, jobs, serviços externos, shells e escritores alternativos. Sem comprovação de drenagem, não migrar. Não revogar postgres nem encerrar indiscriminadamente sessões compartilhadas do Supabase. Registrar janela e providenciar conferência das notificações financeiras afetadas; não presumir que todos os webhooks serão reenviados.

## Verificação e migração — somente após backup e drenagem

```bash
psql --dbname='service=resumao_admin' -X --set=ON_ERROR_STOP=1 --file=preparacao/preflight022_leitura.sql
# Comparar cadastros e vínculos atuais; os cinco Gerais são referência histórica.
# Conferir também schema compatível se coluna/tabela já existirem.
psql --dbname='service=resumao_admin' -X --set=ON_ERROR_STOP=1 --file=backend/migrations/022_tipos_administrador.sql
psql --dbname='service=resumao_admin' -X --set=ON_ERROR_STOP=1 --file=preparacao/postflight022_leitura.sql
```

Executar o arquivo integral; não envolver em outra transação nem remover BEGIN/COMMIT/timeouts. Se falhar, interromper e confirmar rollback por leitura. Se o resultado do COMMIT for desconhecido, verificar o estado antes de repetir. Não iniciar backend sem schema confirmado. Comparar identidades/tipos/estado dos Gerais e valores/vínculos acadêmicos/comerciais, além das contagens.

## Inicialização e recuperação

Após confirmar COMMIT e integridade, restaurar somente o Start Command para o mesmo SHA seguro aprovado, mediante autorização no Render:

```text
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Confirmar SHA Live, runtime/build, saúde, login, /me, negações anônimas das quatro rotas sem gravação, frontend versionado e Bearer; operações positivas em produção somente se legítimas e autorizadas. Os testes de gravação devem ficar na homologação. Restritos permanecem sem competências, independentemente de flags.

Se aplicação não iniciar depois da 022, manter schema e manutenção no SHA seguro; recuperar com o mesmo commit/build ou sucessor compatível aprovado. Nunca retornar a cdba603/702b9e5 como backend, nunca remover a constraint/coluna para reabrir no legado. Falha de deploy pode deixar processo anterior atendendo: verificar processo real, não inferir sucesso pela configuração. Restauração integral de backup não é rollback automático e pode apagar operações posteriores; exige autorização e análise próprias.

## Pendências impeditivas para liberar produção

Backup final e restauração demonstrada, build/runtime seguro recuperável, manutenção e drenagem comprovadas, confirmação da conexão efetiva (banco postgres, papel atual, READ COMMITTED), limites/margem do Session Pooler e ensaio de concorrência/rollback/reconexão em pool isolado equivalente. Não há endpoint isolado disponível nesta sessão; não usar produção para testes de gravação. A homologação PostgreSQL direta não comprova o Supavisor. Sem evidência desses itens, não liberar produção.

## Verificação local desta integração

39 testes de autorização/preservação estrutural, 7 testes PostgreSQL 17.6 (incluindo concorrência de processos, migração, falha parcial e recuperação), 7 testes offline de artefatos e 3 testes frontend aprovados. PostgreSQL efêmero sem rede, dados em tmpfs e bancos exclusivos por teste. Nenhum banco persistente ou serviço externo foi usado para gravação. Apenas avisos de depreciação, sem falhas. Não se repetiram as suítes legadas independentes nem o ensaio Chromium já aprovado, pois frontend e aplicação mantêm os mesmos bytes auditados.

Os 24 arquivos não frontend do commit seguro foram preservados byte a byte e este roteiro é o único arquivo adicional. Os pacotes reconstruídos preservam os hashes de fontes anteriores, apesar da nova ancestralidade Git; seu manifesto identifica a base original e o release de fontes, não o novo SHA Git. O operador deve registrar ambos no plano de implantação.
