# E-mails automáticos de pagamento — migration 019

## Escopo e dependências

A migration cria somente public.emails_pagamentos (14 colunas, oito constraints e um índice parcial adicional à chave primária). Não insere mensagens nem altera pagamentos, acessos, notificações ou modo financeiro. Não modifica migrations anteriores; a 013 permanece independente. O backend exige as estruturas 014–018 e checkout seguro 017 já implantados. O SQL inclui BEGIN/COMMIT, lock_timeout de 5s e statement_timeout de 60s. Incompatibilidades provocam rollback. Testada criação e reexecução em PostgreSQL 17.6 descartável.

## Arquitetura

Uma fila persistente por pagamento/tipo é descoberta a partir de dados financeiros já confirmados. Um worker por processo consulta somente a API autenticada de pagamentos e envia pelo Resend fora das transações financeiras. Não cria cobranças. Não conserva conexões durante HTTP. SELECT FOR UPDATE SKIP LOCKED, lease expirável e chave única coordenam instâncias. O domínio financeiro é somente lido; falhas de e-mail não desfazem aprovação ou acesso.

Somente checkouts seguros criados após o corte explícito são elegíveis. O INSERT de novos checkouts registra criado_em; nenhuma data histórica é preenchida. Transações adicionais herdam a elegibilidade da raiz, mas possuem mensagens e chaves próprias. Cobranças duplicadas e ocorrências financeiras não geram confirmação de compra.

Pix requer copia/cola com CRC e moeda/valor coerentes, PNG completo com CRCs e dimensões limitadas; boleto bancário requer código de barras/linha com dígitos verificadores e valor coerentes, link HTTPS Mercado Pago e vencimento confiável. Informação incompleta é consultada novamente após cinco minutos, sem envio. Sem vencimento confiável ou formato suportado, permanece a mensagem verdadeira na tela. Não há autenticação da plataforma nos dados enviados ao aluno.

E-mail aprovado requer pagamento aprovado, oportunidade concluída e período/contratação/acesso correspondentes efetivamente disponíveis. Dados apresentados são snapshots reais, incluindo desconto e meses contratados. Não há estorno, bloqueio de acesso ou alteração de regras de contestação.

## Configuração posterior (nenhuma aplicada nesta etapa)

- EMAILS_PAGAMENTOS_ATIVOS: false por padrão; habilitar explicitamente com true.
- EMAILS_PAGAMENTOS_DESDE: corte futuro/de ativação em ISO 8601 com fuso explícito UTC. Exemplo de formato: YYYY-MM-DDTHH:MM:SS+00:00. Não retroceder para incluir histórico sem autorização.
- RESEND_API_KEY: credencial existente do provedor, somente no ambiente privado.
- RESEND_FROM_EMAIL: remetente válido de domínio verificado no Resend.
- EMAILS_PAGAMENTOS_INTERVALO_S: 30 por padrão, permitido 15–300.
- EMAILS_PAGAMENTOS_LOTE: 3 por padrão, permitido 1–5.

Configuração ausente/inválida mantém serviço desativado, sem impedir pagamentos. Usa o pool financeiro existente, sem novo engine; processamento sequencial por worker, com conexão liberada antes de rede. Envios somente em NORMAL; não altera modo nem geração.

## Estados e repetição segura

DADOS_PENDENTES aguarda dados completos; EM_ENVIO representa lease; ACEITO exige recibo persistido do Resend. ERRO e INCERTO exigem tentativa administrativa controlada; SUSPENSO impede envio de cobrança inelegível/dados alterados. Máximo de três tentativas. Nenhuma repetição HTTP automática pelo cliente.

Resend conserva chaves idempotentes por 24 horas. O backend reutiliza exatamente chave e payload congelado, restringindo retomadas a menos de 23 horas do primeiro envio. Após esse prazo, não repete: revisar o provedor antes de qualquer intervenção futura. Aceitação seguida de perda de resposta ou falha de commit pode ser retomada dentro da janela. Não promete exatamente uma entrega nem confirmação de caixa de entrada. Exceder a janela fica INCERTO; não existe reenvio ilimitado.

GET /admin/emails-pagamentos retorna somente metadados operacionais, máximo 100 registros. POST /admin/emails-pagamentos/{pagamento_id}/{PENDENTE|APROVADO}/reenviar agenda tentativa elegível com autenticação administrativa, preservando chave/payload. Não reenvia ACEITO e não cria mensagens históricas. Não inserir/alterar estados manualmente no banco.

A fila guarda destinatário e conteúdo necessário em JSONB privado para repetição idempotente. RLS habilitado, sem políticas públicas, com privilégios públicos/anon/authenticated revogados. Backend deve possuir SELECT/INSERT/UPDATE e BYPASSRLS ou política própria autorizada; postgres atualmente confirmado. Não publicar payloads em logs, consultas administrativas ou frontend. Retenção/expurgo de dados não foi implementada; exige política posterior, sem apagar registros nesta etapa.

## Implantação proposta — depende de autorização

1. Confirmar backup recuperável, ausência de homônimos incompatíveis e privilégios. Manter envios desativados.
2. Aplicar exclusivamente SQL original 019, inteiro em uma transação; validar coluna/constraint/índice/RLS, tabela vazia e modo/geração inalterados. Em erro, interromper; não improvisar correções.
3. Publicar backend com envios ainda desativados; verificar saúde e pagamentos sem mudar modo financeiro.
4. Publicar somente alteração de pagamento_sucesso.html; backend antigo/flag ausente preserva fallback.
5. Configurar remetente verificado, credencial, corte explícito e limites; ativar após autorização. Se rollback de código necessário, deixar 019 aplicada e desativar worker; não reverter pagamentos.
6. Validar novos Pix/boleto completos e uma aprovação já liberada, com autorização específica para e-mail real. Conferir fila ACEITO, recibo e conteúdo recebido; notificações repetidas não geram outro envio. Não repetir testes financeiros reais históricos.

## Limites restantes

Existe corrida externa inevitável entre a última consulta de estado ao Mercado Pago e o envio: a cobrança pode ser paga/cancelada nesse intervalo. São feitas consulta confiável e releitura local, e instruções dizem para não pagar novamente se a compra já foi concluída. O worker nunca muda status financeiro. Aceitação pelo Resend não comprova entrega. Validação real do remetente/domínio e dos e-mails aguarda autorização; testes usam apenas provedores simulados.
