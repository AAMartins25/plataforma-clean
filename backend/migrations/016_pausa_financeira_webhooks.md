# Migration 016 e implantação da pausa financeira

Preparação local. Nenhuma execução em produção ou publicação autorizada.
SQL independente de 013/014/015: cria controle singleton e caixa de entrada,
índice de pendências, identidade e restrições; não altera pagamentos/históricos.
Não inserir essas tabelas nos modelos financeiros nem chamar create_all em produção.
O SQL é transacional; lock_timeout 5s e statement_timeout 60s por comando.
As tabelas têm RLS habilitado, sem políticas públicas; PUBLIC, anon e authenticated
não recebem acesso. Confirmar que o papel SQL do backend é proprietário/superuser
ou BYPASSRLS com privilégios suficientes. Se usar papel restrito, interromper para
definir grants/políticas específicas; não conceder acesso ao cliente para contornar.

## Arquitetura e limites

Estados NORMAL, PAUSADO e RECUPERACAO. A versão
`pausa-financeira-v2-transacional` substitui a barreira em conexão separada.
Cada operação captura modo/geração e um prazo. A conexão da própria transação
financeira valida esses valores e bloqueia a linha de controle antes das gravações,
conservando o bloqueio até commit/rollback. NORMAL usa FOR SHARE; RECUPERACAO
usa FOR UPDATE, serializando as transações de recuperação entre instâncias.
A mudança de modo usa FOR UPDATE: espera transações já protegidas, não requisições
que ainda não tenham iniciado a unidade financeira. Essas requisições antigas
não podem gravar depois, mesmo após reabertura, porque a geração não corresponde.

Não existe pool dedicado de leases. Funções financeiras têm proteção também para
chamadas Python diretas. Autocommit é rejeitado; rollback de savepoint exige
revalidação do bloqueio antes da próxima instrução. Os eventos SQLAlchemy protegem DML financeiro de sessões;
DML financeiro por Connection sem operação explícita é rejeitado. SQL executado
fora desses engines/por driver bruto não participa: inventariar e interromper jobs
externos ou adaptá-los antes da implantação. Não há trigger global de manutenção.

Desconexão da conexão que grava encerra a transação e invalida a operação. Não
retomar a mesma sessão para confirmar novas alterações. Erro de COMMIT descarta
a conexão do pool e exige verificação: pode ter ocorrido rollback ou commit no
servidor sem resposta ao cliente. Consultar estado local e API autenticada antes
de repetir; não inferir ausência de efeito pela resposta HTTP. Reprocessamento
da caixa utiliza a idempotência financeira e a conclusão atômica descrita abaixo.

Cloud SQLAlchemy: DB_POOL_SIZE=5, DB_MAX_OVERFLOW=0, DB_POOL_TIMEOUT_S=3 como
limites iniciais do código, não uma afirmação de capacidade do Supabase.
Pool pre-ping e connect_timeout=5 ajudam aquisição; não substituem a proteção
transacional. Teto por processo = DB_POOL_SIZE + DB_MAX_OVERFLOW; considerar
workers, instâncias e sobreposição de deploys, além de Auth/Storage/PostgREST,
conexões administrativas e outros serviços. Confirmar pooler (session/transaction),
limites de clientes e de backends físicos, max_connections, timeouts e margem
antes de definir os valores de produção. Não usar pool_size=0 ou overflow=-1.
Prepared statements continuam desabilitados. Não usar statement pooling.

Um consumidor ativo por objeto Protecao/processo, sem fila de espera que reserve
conexão. Em RECUPERACAO há uma transação financeira de consumo por vez em todo
banco, pela linha central exclusiva. Consultas externas podem se sobrepor entre
instâncias; sua quantidade é limitada pelo inventário de processos participantes.
Cada consumidor necessita de uma única conexão para a unidade financeira;
a autenticação administrativa libera sua transação antes do trabalho. Em caso
de saturação, aquisição expira e a notificação permanece recuperável.

FINANCEIRO_DURACAO_MAXIMA_S=60 (permitido 5..120) é o orçamento da operação.
Recuperação: padrão um evento, máximo cinco, com o mesmo prazo para todo lote.
A rota HTTP encerra com 503 ao atingir o orçamento. Uma consulta externa já
iniciada pode terminar depois: o consumidor conserva seu limite de concorrência
até sair, mas não pode iniciar novas gravações/confirmar após o prazo. Não tratar
503 como cancelamento do pagamento. Consultar a fila antes de repetir.
Locks financeiros têm espera até 3s e statement_timeout limitado pelo prazo restante.
Limites de conexão/leitura HTTP também consideram o prazo restante; não equivalem
a cancelamento remoto de uma chamada já enviada.

O gate HTTP cobre checkout, retorno, revalidação, solicitação/aprovação/recusa e
registro/confirmação de reembolso, concessão administrativa e demonstração.
Consultas e estudo seguem disponíveis. A validade do acesso e as regras comerciais
não são modificadas. A confirmação inicial de estado não substitui os locks de
cada transação. Nenhuma instância sem proteção pode permanecer atendendo.

Checkout: antes do POST de criação de preferência, persistir a identidade local
com estado técnico CHECKOUT_INDEFINIDO, sem aprovação ou acesso. Após resposta
válida, guardar a preferência e retornar PENDENTE. Falha externa/commit incerto
preserva o registro; outra abertura para a oportunidade espera no máximo 3s,
sem reservar conexão, e bloqueia se não houver resultado conhecido. Não reenviar
silenciosamente o POST. Confirmar em produção, por catálogo, que pagamentos.status
aceita o estado técnico (modelos atuais usam varchar(50)); se houver enum/check
incompatível, interromper e solicitar autorização estrutural, sem adaptar o SQL.

Se existir pagamento no provedor para essa identidade, reconciliar pela consulta
individual confiável e merchant order; o backend definitivo recupera a preferência
com prova de identidade, referência e presença da transação na ordem. Se não existir
pagamento/resultado verificável, manter bloqueado para conferência administrativa:
a busca de pagamentos não comprova inexistência de preferência não utilizada.
Não liberar acesso nem remover o registro por suposição. Chamadas externas não
são revertidas por rollback. O lock comercial durante criação de preferência e
a consulta de merchant order necessária à identidade ainda podem atravessar rede;
adotar os timeouts/limites e não declarar atomicidade distribuída.

Webhooks: validar assinatura antes de armazenar; persistir somente payment_id,
hash da identidade do evento, fonte, datas e controle de processamento. Não guardar
payload pessoal, token ou segredo. Retornar sucesso após commit durável. Cada evento
novo do mesmo pagamento tem sua identidade; entrega repetida é deduplicada.
O processamento reivindica a notificação pela mesma Session/conexão do domínio.
Na unidade do consumidor, commits internos do processador tornam-se flush;
alterações financeiras e conclusão da notificação são confirmadas num único commit.
Falha antes desse commit reverte ambos; queda após commit pode deixar resultado
incerto ao cliente, mas a caixa e o domínio permanecem consistentes. Não há worker
externo: recebimento tenta processar em NORMAL; recuperação administrativa ocorre
em RECUPERACAO. Falhas preservam a fila e registram erro neutro quando possível.
Consulta inicial de pagamento ocorre antes da transação financeira, sem reservar
conexão. A pesquisa paginada continua descobrindo transações sem registro local.
Caixa vazia não comprova cobertura no provedor.

## Preparar versão intermediária (somente local)

```bash
PYTHONDONTWRITEBYTECODE=1 python backend/preparar_backend_pausa.py --destino /tmp/resumao-pausa-bootstrap
```

O destino deve ser novo. O script exporta backend HEAD e acrescenta somente o módulo
de proteção, documentos/SQL 016 e integração ao main anterior. Não copia os modelos
novos nem a lógica 014/015. A origem fica em ORIGEM.txt. Verificar o SHA de origem
antes de usar: HEAD deve continuar sendo a versão anterior aprovada. Não publicar
o checkout de trabalho atual como versão intermediária. Esta exportação não é um
commit nem um deploy; seu empacotamento/publicação exigem autorização própria.

## Procedimento futuro, com autorização em cada etapa

1. Confirmar projeto, backup recuperável, horário do backup e exposição sem PITR.
   Conferir ausência de objetos homônimos 016, permissões DDL e tamanho das tabelas.
2. Autorizar e aplicar SQL 016 integral por conexão administrativa. Conferir:

```sql
SELECT id, modo, geracao FROM public.controle_financeiro;
SELECT table_name,column_name,data_type,is_nullable,column_default
FROM information_schema.columns WHERE table_schema='public'
AND table_name IN ('controle_financeiro','notificacoes_mp') ORDER BY table_name,ordinal_position;
SELECT conname,pg_get_constraintdef(oid),convalidated FROM pg_constraint
WHERE conrelid IN ('public.controle_financeiro'::regclass,'public.notificacoes_mp'::regclass);
SELECT indexname,indexdef FROM pg_indexes WHERE schemaname='public'
AND tablename IN ('controle_financeiro','notificacoes_mp');
SELECT estado,count(*) FROM public.notificacoes_mp GROUP BY estado;
SELECT c.relname,c.relrowsecurity,pg_get_userbyid(c.relowner) AS proprietario
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='public' AND c.relname IN ('controle_financeiro','notificacoes_mp');
SELECT tablename,policyname FROM pg_policies WHERE schemaname='public'
AND tablename IN ('controle_financeiro','notificacoes_mp');
```

3. Autorizar publicação da versão intermediária. Seu startup exige controle 016
   acessível e privilégios operacionais; não exige colunas 014/015. Conferir Render Deploys, SHA ativo,
   fim da implantação e encerramento de cada instância/processo anterior, inclusive
   serviços escalados/jobs separados. Logs de shutdown e inventário de serviços são
   necessários; repetir uma consulta pública não comprova todas as instâncias.
   GET /admin/financeiro/manutencao (Bearer de administrador, sem expor token)
   retorna versao_protecao, commit_implantado, backend_definitivo=false, modo/geracao.
4. Autorizar POST /admin/financeiro/manutencao com
   {"modo":"PAUSADO","geracao":<valor atual>,"motivo":"Implantação 014/015"}.
   Confirmar resposta e GET indicando PAUSADO; só então as transações protegidas estão drenadas; operações antigas
   ficam impedidas de novas gravações pela geração. 503 financeiro não significa pagamento cancelado/rejeitado.
5. Com pausa mantida, autorizar 014; validar seu procedimento; autorizar 015; validar.
   Manter os quatro testes antigos sem aprovado_em intactos. Não executar 010/013.
6. Autorizar publicação definitiva. O startup PostgreSQL recusa ausência das colunas
   de 014/015 e da linha 016; essa verificação não substitui validação completa das
   migrations. Confirmar backend_definitivo=true, SHA e fim das instâncias antigas.
7. Autorizar modo RECUPERACAO com geracao atual. Novas operações públicas continuam
   bloqueadas; somente o consumidor administrativo processa a caixa. POST
   /admin/financeiro/notificacoes/recuperar {"limite":1}; GET
   /admin/financeiro/notificacoes apresenta contagens, sem afirmar cobertura do provedor.
8. Autorizar reconciliação: POST /admin/financeiro/notificacoes/reconciliar com
   {"inicio":"<ISO8601 com fuso>","fim":"<ISO8601 com fuso>","pagina":0}.
   Busca autenticada /v1/payments/search por date_last_updated, sem filtrar status
   nem depender da existência local. Até 50 itens/página, janela até sete dias.
   Percorrer proxima_pagina até NULL; dividir janela se exceder offset permitido.
   Cada resultado entra na caixa e sua identidade/vínculo será validada pelo
   processador financeiro existente via consulta individual e merchant order.
   Repetir recuperação e analisar erros, incluindo transações de outras integrações.
9. Comparar painel de notificações/transações e registros locais com margem antes
   e depois da janela. Pesquisa paginada não é snapshot: repetir a varredura com
   sobreposição e fim atualizado após estabilização para capturar mudanças durante
   a paginação. Comparar totais/IDs em ambiente administrativo restrito. Caixa vazia
   NÃO comprova cobertura; resultados ignorados/incompatíveis permanecem erro para
   investigação, sem alterar vínculos ou reembolsos por suposição.
10. Validar concessão única por oportunidade, cobranças duplicadas rastreáveis,
    preservação de reembolsos e acessos. Autorizar retorno NORMAL com geracao atual,
    motivo e conferencia_provedor=true após a conferência efetiva. O endpoint exige
    ausência de pendências/erros; a confirmação humana não é prova automática.
    Continuar monitorando entregas, erros e processamento.

## Contingência

- 016 falha: ROLLBACK se sessão abortada; não publicar proteção nem contornar guardas.
- Proteção falha no deploy: código anterior permanece; pausa ainda não está garantida.
- Ativação falha: não executar migrations; conferir estado e operações/locks ativos.
- Persistência webhook falha: responder erro; conferir painel e reconciliar depois.
  Não desativar a URL, não responder 200 com página de manutenção.
- 014 aplicada/015 falhou: manter PAUSADO e 014; não publicar definitivo.
- Ambas aplicadas/deploy falhou: manter proteção intermediária e PAUSADO; corrigir
  publicação. Não remover colunas, restaurar backup ou voltar ao código sem gate.
- Recuperação falha: eventos ERRO permanecem; reexecutar após diagnóstico. Falha próxima ao commit exige leitura da caixa e conferência do domínio/provedor
  antes de repetição; conclusão e efeito financeiro usam o mesmo commit.
- Novos dados financeiros existem: não retornar ao backend antigo sem capacidade
  de reconhecer filhos. Sem estorno automático, reembolso automático ou alteração
  comercial para resolver pendências. Restauração de backup é último recurso com
  autorização separada; backup diário sem PITR pode perder dados desde o backup.

Documentação primária consultada para paginação e transição do Render:
https://www.mercadopago.com.br/developers/pt/docs/subscriptions/additional-content/payment-management
https://render.com/docs/deploys

## Validação local

A revisão transacional acrescenta testes de término real de conexão no PostgreSQL,
commits intermediários, reabertura/geração antiga, resultados de commit incertos
antes/depois de sua efetivação, pools independentes, recuperação HTTP autenticada
com pool de uma conexão, prazos, DML direto e checkout externo incerto.
Regressão executada: 177 testes SQLite, 60 testes PostgreSQL 17.6 da rodada
completa e 63 testes frontend. A conferência complementar passou em 35 testes: 29 PostgreSQL (incluindo
startup, autocommit e savepoint) e seis testes puros de configuração. Há
sobreposição entre rodadas: são 63 cenários PostgreSQL distintos. Todos sem skips
nas execuções informadas.
As suites usam somente localhost compras_test_* e APIs simuladas.

Os testes não comprovam capacidade/roles/timeouts do Supabase real, substituição
das instâncias do Render ou cobertura na conta Mercado Pago. Confirmar esses
pontos e backup recuperável antes da implantação. Os SQLs 013..016 permanecem
inalterados; não houve operações de produção ou publicação. As sete falhas antigas
de concessão administrativa não foram corrigidas nesta etapa.
