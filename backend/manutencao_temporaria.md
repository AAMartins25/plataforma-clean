# Manutenção temporária do serviço Render

Preparação local: nenhuma configuração de produção foi alterada. Este servidor
usa somente a biblioteca padrão Python, não importa `app`, não lê dotenv ou
DATABASE_URL e não abre conexões de saída. Não exige migrations nem modelos.
Até 16 threads atendem conexões; sockets têm timeout de cinco segundos. Saturação
retorna 503 quando possível. Solicitações HTTP malformadas podem receber 400 ou
encerramento da conexão, nunca confirmação de webhook.

## Comandos e health check

Se o Root Directory do Render é `backend`, o Start Command temporário é:

```text
python -u manutencao_temporaria.py
```

Se o Root Directory é a raiz do repositório:

```text
python -u backend/manutencao_temporaria.py
```

Usa `0.0.0.0` e a variável PORT fornecida pelo Render (padrão local 10000).
O Health Check Path temporário é exatamente `/__maintenance_health`: GET e HEAD
respondem 200 com indicação de manutenção. Todas as outras rotas/métodos válidos,
incluindo POST nesse caminho, respondem 503 com Retry-After de 60 segundos.
Não usar `/`, `/health` ou a URL do webhook como health check HTTP desta versão.
Não há processamento, armazenamento ou confirmação de notificações.

## Ativação futura, dependente de autorização

1. Registrar Start Command, Health Check Path, Root Directory, SHA e configurações
   originais; não copiar credenciais. Desativar Auto-Deploy de backend e frontend,
   conferir deploys pendentes e automações. Aprovar separadamente commit/push dos
   arquivos deste mecanismo, sem incorporar o backend definitivo 014/015.
2. Confirmar que Build Command e Pre-Deploy Command não importam a aplicação,
   executam migrations nem estabelecem conexões financeiras. Este servidor não
   protege outros comandos/processos; interromper se houver algum desses efeitos.
3. Preparar o SHA intermediário aprovado. A 016 deve estar validada antes do
   startup intermediário, mas não é necessária para este servidor temporário.
4. Autorizar a mudança do Start Command e Health Check Path e o deploy de
   manutenção. Coordenar as duas configurações para que o candidato tenha health
   check compatível; não publicar antecipadamente lógica definitiva. Se salvar
   configurações disparar deploy, esse disparo também exige autorização e revisão
   prévia do SHA que será utilizado. Não presumir que Auto-Deploy desligado impede
   deploy causado por mudança de configuração.
5. Registrar início da janela. Confirmar deploy ativo, health 200, webhook POST
   503, encerramento de todas as instâncias antigas e liberação de suas conexões.
   O processo temporário abre zero conexões PostgreSQL: antigo + temporário não
   acrescenta posições ao pool. Não iniciar o intermediário só porque o health
   check respondeu. Conferir margem para suas cinco conexões no pool pertinente.

## Desativação e recuperação futuras, dependentes de autorização

1. Autorizar restauração do Start Command Uvicorn **exatamente como registrado**,
   restauração do health check original e deploy do SHA intermediário aprovado.
   Não presumir qual era o comando Uvicorn ou seu caminho de health check.
2. Confirmar que candidato usa comando e health compatíveis; temporário +
   intermediário abre até cinco conexões do backend. Conferir SHA ativo,
   backend_definitivo=false, startup/health e encerramento do processo temporário.
3. Ativar a pausa centralizada somente com autorização própria e após comprovar
   ausência de processos antigos sem proteção. Prosseguir conforme procedimento
   016/014/015 aprovado; não reabrir finanças antes da recuperação necessária.
4. Manter a URL do Mercado Pago intacta. Durante a indisponibilidade notificações
   recebem erro e **não são armazenadas localmente**. Reenvios não garantem cobertura.
   Registrar fim da janela e reconciliar posteriormente pela API autenticada, com
   margens e paginação, incluindo transações sem registro individual local.
   Recuperação administrativa exige o definitivo após 014/015. Nunca usar caixa
   vazia como prova de cobertura ou realizar aprovação/reembolso por suposição.

## Falhas e limites

Se o deploy de manutenção falhar, confirmar qual versão ainda atende. Se o
intermediário falhar, conservar a manutenção com 503, investigar e republicar o
SHA correto; não restaurar automaticamente um backend sem proteção. Não alterar
dados financeiros para resolver falha de implantação. Estudo e demais rotas ficam
indisponíveis durante esta etapa temporária. A duração total inclui builds,
health checks e drenagem: não é garantida pelo servidor. A resposta de saúde é
somente liveness deste processo, não prontidão da aplicação financeira.

Teste local (não importa a aplicação e não requer PostgreSQL):

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s backend -p test_manutencao_temporaria.py -v
```

O subprocesso de teste bloqueia imports de aplicação/drivers, leitura de variáveis
PostgreSQL/dotenv e chamadas de conexão de saída, enquanto recebe requisições HTTP
reais em loopback. Isso testa o servidor, não comprova comandos de build/startup,
capacidade do pool ou encerramento de instâncias reais do Render.
