# Backend financeiro definitivo consolidado — preparação local

Parecer: PRONTO para revisão/criação de commit, não autorizado para publicação.
Worktree: /tmp/resumao-definitivo-worktree
Branch: preparacao-financeira-definitivo
Base exata: f36e2a1c8008a8f9cc0445397d292cb6d5460d43 (M2).
HEAD permanece M2; não houve commit, push, deploy ou execução de migrations.

## Montagem seletiva

Diferenças financeiras de main.py e models.py aplicadas por patches sobre M2;
novo transacoes_mp.py copiado após revisão. Models mantém inclusive o final de
arquivo original de M2: sem alteração cosmética fora dos campos financeiros.
A lógica e o pool em pausa_financeira.py, financeiro_transacional.py, database.py,
contratacoes.py e oportunidades.py permanecem idênticos a M2. Servidor/documento de
manutenção M2 preservados. Seu teste de GET / foi ajustado para testar somente
saúde sem SQL no backend completo: as premissas do esquema intermediário continuam
na suíte do preparador, que exporta a origem anterior explicitamente fixada.

O definitivo ativa definitivo=True pelo padrão de instalar. Startup consulta o
controle e valida estruturas de 014/015 e permissões de 016, sem redefinir modo
ou geração. database.py conserva a inicialização create_all preexistente; não é
executor de migrations e não foi importado contra PostgreSQL nesta validação.
O estado existente PAUSADO/1 foi preservado ao reinstalar a proteção na fixture,
com DML proibido nesse intervalo. A inbox é durável, deduplicada, e seu consumo
confirma efeito financeiro e conclusão em uma mesma transação. Modo RECUPERACAO
exige ação administrativa explícita; NORMAL exige conferência e ausência de fila
pendente/erro. Aprovações duplicadas geram ocorrência, não segunda liberação.
Reembolso manual exige solicitação do aluno; confirmação registra administrador
logado e preserva acesso em cobrança duplicada sem período. Não há estorno ou
transferência automática ao provedor.

## Manifesto local — arquivos em relação a M2

1. `backend/app/main.py`
2. `backend/app/models.py`
3. `backend/app/transacoes_mp.py`
4. `backend/definitivo_consolidado.md`
5. `backend/migrations/014_pagamentos_multiplas_transacoes.md`
6. `backend/migrations/014_pagamentos_multiplas_transacoes.sql`
7. `backend/migrations/015_reembolsos_manual_auditoria.md`
8. `backend/migrations/015_reembolsos_manual_auditoria.sql`
9. `backend/test_admin_reembolsos.py`
10. `backend/test_compras_fluxo.py`
11. `backend/test_confirmar_pagamento.py`
12. `backend/test_definitivo_consolidado.py`
13. `backend/test_financeiro_transacional_pg.py`
14. `backend/test_manutencao_temporaria.py`
15. `backend/test_ocorrencias_financeiras.py`
16. `backend/test_pausa_financeira.py`
17. `backend/test_pausa_financeira_pg.py`
18. `backend/test_prazo_reembolso.py`
19. `backend/test_reembolso_manual_fluxo.py`
20. `backend/test_reembolso_manual_pg.py`
21. `backend/test_revalidacao.py`
22. `backend/test_transacoes_concorrencia_pg.py`
23. `backend/test_transacoes_mp.py`
24. `backend/test_webhook_mercadopago.py`

Os SQLs/documentos 014/015 são os originais, incluídos como rastreabilidade e
suporte das suítes PostgreSQL; não executados. Nenhum arquivo 013 foi transferido
nem incluído. Não copiar diretórios temporários ou snapshots ao futuro commit.
Nenhum frontend integra o diff. A validação frontend separada está somente em
/tmp/resumao-definitivo-frontend-validacao; não publicá-la neste commit backend.

## Testes efetivamente executados

- 183 testes da regressão financeira em SQLite aprovados.
- 6 provas novas de consolidação aprovadas: identidade definitiva, preservação
  de PAUSADO/geração na instalação sem DML, webhook durável durante pausa,
  recuperação explícita mantendo checkout bloqueado, recusa de reabertura com
  inbox pendente e campos/modelos + arquivos de proteção preservados.
- 9 testes de manutenção/saúde aprovados, incluindo GET / do backend completo
  com SQL proibido durante a requisição. Servidor temporário testado com imports
  de aplicação/drivers, variáveis PostgreSQL, dotenv e saída de rede bloqueados.
- 4 testes do preparador aprovados, incluindo 7 cenários da exportação antiga.
- 4 arquivos Node aprovados: compras, retorno, reembolso aluno e reembolso admin,
  na cópia de frontend separada. Não representar essa validação como deploy.
- AST/sintaxe, git diff --check, conteúdo novo e manifesto conferidos; sem padrão
  de chave privada/token real encontrado no diff. Exemplos de teste são sintéticos.

Todos os efeitos financeiros foram exclusivos das fixtures SQLite com APIs
simuladas. Testes PostgreSQL/conexões independentes não foram reexecutados, pois
suas fixtures executam migrations, vedadas nesta autorização. Suites PG relevantes
foram incorporadas para rodada futura explicitamente autorizada. Os sete testes
historicamente falhos de concessão administrativa não foram corrigidos/reavaliados.
Avisos existentes de Pydantic/datetime permaneceram, sem falhas na seleção executada.

## Preservação e próxima etapa

Workspace principal preservado por snapshot de branch, HEAD, status, staging,
lista de arquivos e hashes de todos os arquivos rastreados/não rastreados,
incluindo os três pendentes de 013. Registro somente em /tmp.
A branch de preparação intermediária e main não mudaram. Nada acessou produção.

Autorizar separadamente revisão final/staging/commit deste manifesto. Após futuro
commit, conferir o artefato exato antes de push/deploy autorizados. Na implantação,
manter PAUSADO e usar uvicorn app.main:app --host 0.0.0.0 --port $PORT, Health Check
/, Auto-Deploy Off e SHA específico. Não reabrir ou reconciliar sem autorização.
Comparar fila e pesquisa paginada do provedor para recuperar notificações da janela
503, inclusive transações sem registro individual local; fila vazia não prova
cobertura. Sob sobreposição, confirmar margem para dois pools de cinco conexões.
Após efeitos novos, não retornar M2 a operação normal; conservar pausa e reparar
a versão definitiva. Recuperação/reabertura são etapas financeiras distintas.
