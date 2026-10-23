# Homologação local complementar — intermediário — 23/10/2026

Somente worktree /workspaces/resumao-intermediario-seguro, base cdba603e9a8d3a3a04a77fc03863ad41c93c1a93. Nenhum commit/push/deploy ou alteração em produção/credenciais/serviços externos. Patch de aplicação e seus 12 arquivos originais permanecem com os hashes anteriores. Principal: 6.979 arquivos preservados.

## Ensaios novos, sem repetir a regressão completa

1. `backend/test_homologacao_cache_intermediario.py`: um teste integrado aprovado em Chromium completo local, com HTTP local e handlers reais sobre SQLite. Scripts antigos e handlers publicados são extraídos do commit-base. API_BASE é redirecionada apenas na resposta do servidor do teste, sem modificar app.js. HTTPS externo é bloqueado no navegador, sem uso da produção.
   - Consumidor antigo + API publicada: 200.
   - Consumidor novo + API publicada: 200 com Bearer.
   - Consumidor novo + intermediário: 200 para Geral.
   - Navegador mantém o script antigo em cache, mesmo após o servidor passar ao script novo: comprovado pelo código efetivamente carregado e pelo contador de requisições do asset.
   - Consumidor antigo em cache + intermediário: 401, sem remover o token válido e sem gravar curso.
   - Recarregamento forçado troca o asset: criação funciona com Bearer.
   - Restrito com JWT válido: 403, mesmo com flags ligadas.
   - Criação de disciplina/assunto e associação autenticada também funcionam. A criação de curso usa o listener real do formulário; a associação usa o método real do frontend.
   - Cabeçalhos de cache são deliberadamente controlados no harness (`max-age=3600`). Não são uma medição do cache do Render/CDN. O HTML do harness é mínimo, não uma certificação visual de todas as páginas reais.
2. `backend/test_homologacao_local_intermediario.py`: um teste integrado aprovado em PostgreSQL 17.6, contêiner sem rede, dados tmpfs e banco efêmero exclusivo.
   - Schema e pré-requisitos publicados preparados só na fixture. Massa de 60 usuários, cinco Gerais, vendedor e acesso acadêmico.
   - Interrupção da conexão antes de COMMIT da 022: coluna/tabela novas e alterações transacionais são desfeitas; usuários preservados.
   - Aplicação integral da 022: cinco Gerais e vínculos preservados.
   - Processo independente realiza flush de novo usuário e auditoria; é terminado antes do commit. Nenhum dos dois registros persiste.
   - Outro processo importa exclusivamente o intermediário com engine/pool novos e executa startup/shutdown reais da aplicação. /me e gravação de curso funcionam após reinício.
   - Um perfil restrito continua recusado com 403 após recuperação, inclusive com flag ligada.
   - Usa app.database substituído explicitamente pela factory do banco efêmero, sem ler a conexão configurada para produção. Não é teste do serviço Render.

Logs: evidencias/homologacao-cache.log e evidencias/homologacao-recuperacao.log. Ambos registram `1 passed`. Os ensaios integrados têm diversas asserções; não equivalem à execução de somente uma operação.

As evidências anteriores de pagamentos/vínculos, quatro rotas, autenticação e concorrência foram reaproveitadas; não se repetiram os 467 testes publicados, os 39 específicos nem os seis PG sem necessidade.

## Ajustes exclusivos do harness

Falhas iniciais foram causadas por massa de cursos com defaults/serial incompletos, coleta de uma função auxiliar pelo pytest e tempo insuficiente de inicialização/localização da porta do Chromium. Foram corrigidos somente testes/harness. Não houve correção de negócio ou mudança no patch auditado.

## Limitações e pendências

Não foi fornecido endpoint de Session Pooler isolado. Não há binário PgBouncer nem imagem local Supavisor/PgBouncer disponíveis; não foram consultadas conexões de produção nem instalados serviços externos. Permanecem as evidências PostgreSQL/QueuePool locais e a pendência de validação no Session Pooler real de homologação.

Cache antigo pode causar interrupção funcional segura (401) após trocar o backend. Publicar frontend primeiro não comprova atualização de abas/assets já em cache. Antes de produção, definir e verificar revalidação/invalidação de assets ou instrução de recarregamento, confirmando o código entregue e o Bearer nas duas chamadas alteradas. Não foi implementado cache-busting nesta etapa.

Continuam pendentes revisão/identificação de artefato recuperável, roteiro coordenado frontend automático/backend manual, backup restaurável, manutenção/drenagem e inventário dos escritores antigos. Nada foi testado ou alterado no Render/Supabase.

## Conclusão

Homologação local complementar aprovada, sem defeito novo de aplicação identificado. Há comportamento esperado de recusa para frontend antigo em cache. Pode avançar à preparação/revisão do roteiro e do artefato de implantação/recuperação, sujeito a nova autorização. Isso não libera produção nem ativa restritos; não usar cdba603 como recuperação. Nenhum banco persistente foi utilizado. O contêiner efêmero foi encerrado ao concluir.
