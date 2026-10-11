# Manutenção temporária M2 do serviço Render

Preparação local, sem commit ou publicação. O servidor usa somente a biblioteca
padrão Python, não importa app/FastAPI/SQLAlchemy, não lê dotenv ou DATABASE_URL
nem abre conexões de saída. Não exige migrations nem modelos. Até 16 threads
atendem conexões; sockets têm timeout de cinco segundos. Saturação retorna 503
quando possível. HTTP malformado pode receber 400 ou desconexão, nunca confirmação
financeira. Logs não registram URLs, identificadores ou cabeçalhos.

## Saúde e comando

GET e HEAD respondem 200 exclusivamente para os alvos exatos `/` e
`/__maintenance_health`, indicando status maintenance. POST nesses caminhos e
as demais requisições válidas retornam 503 com Retry-After de 60 segundos,
incluindo login, checkout e webhooks. Query strings, barra adicional e `//`
não são considerados caminhos de saúde. HEAD não inclui corpo.

O Health Check do Render permanece HTTP `/` durante toda a transição. Não alterar
seu caminho, Root Directory backend, Build Command ou Pre-Deploy Command vazio.
Com Root Directory backend, o Start Command temporário será:

```text
python -u manutencao_temporaria.py
```

O servidor escuta 0.0.0.0 e PORT fornecida pelo Render (padrão local 10000).
Para o intermediário, o comando correto é:

```text
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

`app.main` sem `:app` é inválido para Uvicorn. No commit I, a rota GET `/` do
intermediário já responde 200 sem consultar o banco. O teste M2 confirma isso
no backend completo, com qualquer instrução SQL proibida durante a requisição.

## Preparação e transição futuras, cada uma mediante autorização

1. M2 será filho de I na branch preparacao-financeira-016, preservando M/I/main.
   Alterar somente este documento, o servidor temporário e seus testes.
   O mesmo SHA M2 conterá o servidor e o intermediário já aprovado: não exige I2.
2. Autorizar separadamente commit/push e implantação. Manter Auto-Deploy Off,
   branch configurada main e HTTP Health Check `/`. Conferir SHAs, processos,
   ausência de deploys pendentes e margem do pool. Não assumir que Auto-Deploy
   Off impeça deploy causado pelo salvamento no Dashboard.
3. Pela API Update service, preparar somente o Start Command de manutenção:
   a documentação informa que a atualização não dispara deploy automaticamente.
   Conferir configuração e disparar separadamente o deploy pelo SHA M2 explícito.
   Não incluir buildSourceId, mudanças de branch ou configurações extras.
4. Registrar início da janela. Confirmar SHA M2 LIVE, GET `/` 200 indicando
   maintenance e POST de webhook 503. A mudança de Start Command não comprova
   encerramento do antigo. Aguardar shutdown de todas as instâncias Uvicorn
   antigas, requisições encerradas e liberação de suas conexões. O temporário
   abre zero conexões PostgreSQL. Conferir margem para as cinco do intermediário.
5. Autorizar restauração exclusivamente do Start Command Uvicorn acima pela API
   e outro deploy do MESMO SHA M2. Manter Health Check `/`. A 016 precisa estar
   aplicada/validada; não executar migrations neste procedimento. Confirmar
   backend_definitivo=false, versao_protecao=pausa-financeira-v2-transacional,
   SHA M2, saúde e encerramento do temporário. Variáveis efetivas do pool precisam
   manter tamanho cinco e overflow zero. O candidato protegido executa seu startup
   de validação antes de responder saúde; o 200 de `/` sozinho não prova a proteção.
6. Ativar a pausa centralizada somente com autorização própria e após conferir
   ausência de instâncias antigas. Recuperação administrativa/reconciliação exige
   o definitivo após 014/015; não tentar habilitá-la no intermediário.

## Contingência e notificações

Conservar os dois comandos e os artefatos. Se um deploy falhar, conferir qual
processo continua atendendo; não presumir que ocorreu troca. Se o intermediário
falhar, manter/restaurar a manutenção com seu Start Command e o SHA correto,
mediante autorização. Não restaurar automaticamente backend sem proteção.

A URL do Mercado Pago permanece intacta. Durante a manutenção toda a aplicação
fica indisponível; webhooks recebem erro e NÃO são armazenados localmente.
Registrar início/fim da janela e reconciliar depois pela API confiável com margens,
paginação e transações ainda sem registro local. Não depender exclusivamente dos
reenvios, não usar caixa vazia como prova de cobertura e não aprovar/reembolsar
por suposição. Liveness da manutenção não significa prontidão financeira.

## Validação local

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s backend -p test_manutencao_temporaria.py -v
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s backend -p test_backend_intermediario.py -v
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=backend python -m pytest -q -p no:cacheprovider backend/test_financeiro_transacional.py
```

O servidor de teste recebe HTTP real em loopback enquanto imports da aplicação e
banco, variáveis PostgreSQL, dotenv e conexões de saída são proibidos. Testes
cobrem os dois caminhos, métodos, variantes, login/webhooks, concorrência,
saturação, recuperação e SIGTERM. O backend completo é testado em subprocesso
com SQLite exclusivo da fixture e Mercado Pago simulado, sem migrations; GET `/`
é executado com SQL bloqueado. Nada acessa produção. Testes não comprovam shutdown
no Render nem cobertura de notificações no provedor.
