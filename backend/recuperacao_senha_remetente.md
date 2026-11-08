# Remetente da recuperação de senha

A recuperação passa a enviar de `Resumão Online <contato@resumaoonline.com.br>`,
com o assunto `Resumão Online - Redefinição de senha`. O corpo utiliza a mesma
marca. A alteração de aplicação se limita a essas três strings em `app/main.py`.
Busca da conta, geração aleatória do token, hash SHA-256, validade de 30 minutos,
transação e redefinição permanecem como antes.

## Configuração

Não há variável nova nem necessidade de alterar `RESEND_FROM_EMAIL`: essa variável
é exclusiva do fluxo de pagamentos e permanece intacta. A recuperação continua
usando `RESEND_API_KEY` e `APP_BASE_URL` existentes.

O domínio já foi informado como verificado pelo solicitante. Antes de uma futura
publicação, conferir por leitura que a chave efetivamente usada pelo backend
pertence à conta/equipe que verificou `resumaoonline.com.br` e tem permissão para
enviar por esse domínio. Conferir também que `APP_BASE_URL` aponta para o site
público HTTPS. Nenhuma dessas configurações foi alterada ou consultada em produção.

Não alterar flags, remetente, payloads, hashes ou estados da fila de pagamentos.
Não há migration nem intervenção em dados neste ajuste.

## Validação isolada

Na raiz da worktree:

```sh
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -p no:cacheprovider backend/test_recuperacao_senha.py
```

Os testes carregam a aplicação com banco substituído por SQLite em memória,
dotenv desabilitado, credenciais sintéticas, pagamentos desativados, Resend
simulado e bloqueio de rede. Cobrem recuperação por e-mail/CPF, destinatário,
marca, hash e validade do token, preservação dos dados, contas ausentes,
falhas de envio e commit, redefinição e rejeição de token usado/expirado/inválido.

Comportamento existente preservado: o envio antecede o commit. Se o provedor
aceitar a mensagem e o commit falhar, a resposta continua sendo 500 e o rollback
impede a persistência do novo token. O link dessa tentativa fica inválido. O teste
de falha de persistência verifica esse cenário; este ajuste não altera a ordem.

Resultado: **9 testes passaram**. Foram emitidos avisos de depreciação das
dependências e do uso existente de `datetime.utcnow()`, sem falhas nos testes.
As funções reais das rotas foram chamadas diretamente; o executor HTTP
`TestClient` travou neste ambiente e suas tentativas foram encerradas. Não há
validação HTTP ponta a ponta neste resultado.

Integração/publicação e qualquer teste com envio real ficam para aprovação
posterior. Não foram realizados commit, push ou deploy.
