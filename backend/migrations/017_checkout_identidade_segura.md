# 017 — Identidade segura de checkouts futuros

Preparação local, baseada em aea68a6396517f3cfc990cee475759cde87b71ea.
Não aplicar sem autorização específica. Nenhuma alteração retroativa de pagamentos.

## Vínculo

Cada nova raiz recebe o snapshot imutável checkout_meses do prazo contratado, checkout_identidade, gerada por secrets.token_urlsafe(32)
(256 bits), e checkout_recebedor_id. Ambas são persistidas antes do POST de
preferência, com usuário, curso, período, valor, moeda e oportunidade.
A resposta de criação deve identificar o recebedor esperado; referência divergente, se devolvida, também bloqueia a confirmação local.
A referência enviada é checkout:<identidade>. Ela não deve aparecer em logs.
Transações filhas não recebem outra identidade: continuam vinculadas à raiz.

A consulta autenticada de payment deve devolver exatamente essa referência,
collector_id coincidente com o recebedor persistido e configurado, live_mode
booleano true, valor exato, moeda BRL, ID correto e status financeiro aceito.
Os locks e a unicidade global de mp_payment_id permanecem os existentes.
Uma segunda aprovação é registrada como cobrança duplicada sem outro acesso.

O objetivo passa a ser comprovar a intenção de checkout. A identidade não é
um identificador de preferência e não demonstra, isoladamente, uma preferência
específica. A preferência conhecida vem da resposta autenticada de sua criação;
ela não é inferida do payment. Não se preenche preferência desconhecida.
CHECKOUT_INDEFINIDO sem preferência continua bloqueado, inclusive diante de um
payment aprovado. Nenhum fallback fraco para os registros legados foi criado.

## Recebedor — requisito de implantação

MP_COLLECTOR_ID deve ser a identidade da conta recebedora de produção confirmada
pelo proprietário no painel Mercado Pago ou por consulta autenticada de identidade
da conta, em etapa separadamente autorizada. Não usar o collector_id do pagamento
que se pretende aceitar como fonte dessa configuração. Não copiar Access Tokens.
Sem recebedor configurado, novos checkouts falham fechados. Mudança da configuração
não altera checkouts persistidos; divergências bloqueiam seu processamento.

## Migration

017 é independente da 013; exige pagamentos e campos das 014/015. Não altera 013–016.
Adiciona três colunas nullable sem default, índice único e trigger de integridade.
Não executa UPDATE/backfill. Registros antigos permanecem com os campos NULL.
Não modifica estados financeiros ou de manutenção. Usa uma transação,
lock_timeout 5s e statement_timeout 60s. Falhas exigem ROLLBACK na sessão antes
 de nova tentativa. Trigger protege identidade, recebedor e snapshot financeiro;
impede retrofit de históricos e exclusão de raízes seguras. Permite os updates
financeiros normais e o primeiro registro da preferência; depois a preferência
é imutável. Rodar novamente apenas com mesma versão aprovada.

Antes: confirmar backup recuperável recente, pausa ativa, ausência de locks
longos e dos nomes homônimos incompatíveis. Validar dependências sem expor dados.
Não habilitar vendas se campos, índice ou trigger estiverem incompatíveis.
Após: conferir as colunas (varchar43/varchar64/integer, nullable, sem default), índice único
válido, função e trigger BEFORE INSERT/UPDATE/DELETE habilitado; contagens e
conteúdo anteriores preservados. Não imprimir identidades nos resultados.

## Fluxo incerto

Timeout, HTTP de erro, JSON inválido ou resposta incompleta de criação deixam a
identidade durável em CHECKOUT_INDEFINIDO. Nova tentativa não cria outra raiz,
oportunidade ou preferência para a mesma oportunidade incerta. Não há retry
externo automático. Um resultado tardio conhecido pode ser gravado pela operação
original dentro das proteções existentes. Recuperação adicional exige evidência
forte e procedimento específico, não implementado nesta etapa.

## Implantação futura (não autorizada)

1. Revisar e autorizar commit/push e diagnósticos da 017 separadamente.
2. Confirmar recebedor e retorno exato de external_reference em Checkout Pro
   no ambiente de validação apropriado, sem usar dados reais de alunos.
3. Com pausa preservada e backup confirmado, aplicar 017 após autorização.
4. Configurar o recebedor confirmado e publicar backend após autorização.
5. Validar SHA, modo e geração preservados, endpoints e testes direcionados.
6. Resolver pendências da fila pelo fluxo autorizado; esta arquitetura não
   elimina a condição de fila concluída para reabrir vendas nem corrige o 403 legado.
7. Reabertura e compra real de teste exigem novas autorizações.

Não publicar este backend antes da 017: o ORM passa a depender das novas colunas.
Rollback para a versão anterior pode preservar as colunas adicionais, mas essa
versão não entende novas referências; pausar finanças durante contingência.
RLS e privilégios permanecem os existentes de pagamentos. Nenhuma infraestrutura
nova é necessária. Logs HTTP/SQL externos também devem manter redaction de
referências, e SQLAlchemy echo não deve ser habilitado em produção.
