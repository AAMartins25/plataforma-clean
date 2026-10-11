# Validação local do backend intermediário

Resultado: APROVADO na preparação local, sujeito às validações operacionais e à
autorização de implantação. Nenhuma migration, commit, push ou deploy executado.

Origem revisada: `c42eb6a919b1da1bf1ab578a3d036543aeaa4d71`.
Artefato revisado: `/tmp/resumao-intermediario-final-20261011/backend`.
O diretório é temporário; regenerar e comparar antes da publicação autorizada:

```bash
PYTHONDONTWRITEBYTECODE=1 python backend/preparar_backend_pausa.py \
  --origem c42eb6a919b1da1bf1ab578a3d036543aeaa4d71 \
  --destino /tmp/resumao-intermediario-revisado
```

O destino deve ser novo. O parâmetro opcional `--origem` evita trocar a base
silenciosamente após um commit. O preparador continua compatível com chamadas
anteriores que não informam a origem. Não exportar o HEAD definitivo 014/015.

## Manifesto do futuro commit intermediário: 12 arquivos

Usar os quatro arquivos modificados **da exportação**, comparados à origem:

1. `backend/app/main.py`
2. `backend/app/database.py`
3. `backend/app/contratacoes.py`
4. `backend/app/oportunidades.py`

Acrescentar os módulos/SQL/documento copiados pelo preparador:

5. `backend/app/financeiro_transacional.py`
6. `backend/app/pausa_financeira.py`
7. `backend/migrations/016_pausa_financeira_webhooks.sql`
8. `backend/migrations/016_pausa_financeira_webhooks.md`

Acrescentar ferramentas, testes e esta conferência do workspace:

9. `backend/preparar_backend_pausa.py`
10. `backend/test_backend_intermediario.py`
11. `backend/test_financeiro_transacional.py`
12. `backend/intermediario_prontidao.md`

Não fazer staging diretamente do `main.py` atual do workspace: ele contém a
implementação definitiva. A montagem posterior exige checkout isolado baseado
na origem revisada, transferência dos arquivos intermediários e revisão do diff.
Não incluir `ORIGEM.txt`, diretórios de /tmp, alterações do frontend, models.py,
schemas.py, transacoes_mp.py, SQLs 014/015 nem seus testes definitivos.
Os três arquivos da 013 ficam fora e intactos. Os três arquivos de manutenção
temporária constituem outra preparação; não pertencem a este manifesto.

## Verificações efetivamente executadas

- Exportação pelo preparador e comparação de todos os arquivos com a origem:
  somente quatro alterações e quatro novos arquivos no artefato executável.
- Models e schemas idênticos à origem; sem frontend ou módulo transacoes_mp;
  nenhuma nova coluna de 014/015 nos modelos usados nos testes.
- Quatro testes do preparador aprovados, incluindo execução em subprocesso do
  backend exportado com sete cenários funcionais aprovados: identidade da versão,
  gate financeiro, assinatura/persistência/deduplicação de webhook na pausa,
  bloqueio da recuperação definitiva, checkout normal, checkout incerto sem
  reenvio e pool cloud real sem abrir conexão PostgreSQL.
- Seis testes puros existentes de configuração do pool aprovados.
- Syntax/diff e hashes dos arquivos protegidos conferidos.

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover \
  -s backend -p test_backend_intermediario.py -v
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=backend \
  python -m pytest -q -p no:cacheprovider backend/test_financeiro_transacional.py
```

SQLite foi exclusivo das fixtures; APIs externas simuladas e conexões de saída
bloqueadas por audit hook. app.database foi substituído no teste HTTP, evitando
seu create_all de inicialização. O engine cloud foi validado pela expressão
create_engine exportada, sem conexão ou inicialização do módulo database.
Nenhum script SQL de migration foi executado nesta rodada. PostgreSQL/RLS/locks
não foram reexecutados: testes anteriores não são apresentados como novos.
Há avisos de depreciação preexistentes de Pydantic/datetime, sem falha nesta suíte.

## Dependências operacionais antes da implantação

- Aplicação autorizada e validação da 016; acesso do postgres às tabelas novas.
- Confirmar `DB_POOL_SIZE=5`, `DB_MAX_OVERFLOW=0`, `DB_POOL_TIMEOUT_S=3` efetivos
  (estes são os padrões; variáveis existentes podem sobrescrevê-los).
- Auto-Deploy desligado e publicação exclusiva do SHA intermediário revisado.
- Passagem pelo processo temporário sem banco e encerramento do backend antigo,
  sem sobrepor seu teto de 15 ao intermediário de cinco.
- Validação pós-deploy: versao_protecao=pausa-financeira-v2-transacional,
  backend_definitivo=false, SHA autorizado e proteção instalada em todas instâncias.
- Não iniciar RECUPERACAO no intermediário. Reconciliar a janela somente após
  014/015 e backend definitivo; não considerar fila vazia prova de cobertura.
