# Preparação de implantação — intermediário seguro — 23/10/2026

## Estado e autorizações

Somente preparação local. Nenhum commit, push, deploy, migração persistente, alteração de credencial ou serviço externo foi executado. Workspace principal preservado. Restritos continuam bloqueados, mesmo com flags ligadas. Não alterar DATABASE_URL nem desativar postgres.

A aplicação/backend auditados permanecem intactos. O ajuste adicional é exclusivamente frontend: um asset administrativo com hash e 18 referências HTML. Novos scripts de preparação, testes e artefatos não são carregados pela aplicação.

## Entregas e identidade

- `artefatos/frontend-compativel.tar.gz`: somente site-html, com todas as páginas publicadas preservadas e as mudanças compatíveis. É PROIBIDO usá-lo para backend/recuperação.
- `artefatos/backend-intermediario.tar.gz`: fontes completas da base cdba603e9a8d3a3a04a77fc03863ad41c93c1a93 mais o patch administrativo auditado e o frontend compatível.
- `artefatos/recuperacao-intermediario.tar.gz`: cópia byte a byte do pacote backend seguro, com o mesmo SHA-256. Nunca contém o backend antigo como fallback.
- `artefatos/INDICE.json`, `SHA256SUMS`: identidades, finalidades e hashes. Guardar os hashes aprovados em registro separado e confiável.
- Patches: `frontend-primeiro.patch` e `intermediario-completo.patch`, separados para revisão e futuras integrações autorizadas.
- `artefatos/verificar_artefato.py`: verificador offline, não extrai/importa aplicação, não acessa ambiente ou banco. Exige SHA-256 externo e finalidade; recusa frontend como recuperação, alterações, entradas duplicadas/traversal e arquivos .env/.git.
- `preparacao/construir_artefatos.py`: reprodução determinística a partir do Git-base e lista explícita auditada. Mudanças independentes do worktree não são incorporadas. Arquivo auditado alterado ou HTML fora da troca de URL provoca recusa.

Esses arquivos são FONTES verificadas, não imagem do runtime Render. O HEAD ainda é o SHA-base; as mudanças não estão commitadas. Após autorização, os futuros SHAs de frontend e backend deverão ser registrados e comparados com as fontes dos pacotes. Não selecionar cdba603 ou o commit futuro de frontend como backend seguro.

`backend/requirements.txt` publicado não fixa versões. Ele foi preservado. `DEPENDENCIAS-TESTADAS.json` registra o ambiente local, sem substituir requirements nem ser um lock de produção. Antes de produção, confirmar Python/dependências/build do Render e disponibilizar recuperação executável compatível; os hashes das fontes não garantem um rebuild idêntico de dependências.

## Verificação offline, sem publicação

Ler INDICE.json e copiar o hash aprovado do pacote desejado. Exemplo, substituindo o marcador pelo valor real aprovado:

    python artefatos/verificar_artefato.py artefatos/recuperacao-intermediario.tar.gz --sha256 HASH_APROVADO --uso recuperacao

Não usar o pacote se a verificação falhar. Validar antes do ensaio, da implantação e da recuperação. A verificação técnica do pacote não impede, sozinha, que um operador selecione código inseguro na interface do Render.

## Cache: solução implementada e limite

`admin-intermediario-022.50a3de8ba07dc6ed.js` contém exatamente o admin.js auditado. Dezoito páginas que já carregavam admin.js passam a referenciar esse novo caminho; nenhuma outra alteração HTML foi incorporada. A página que não carregava admin.js permanece sem ele. Manter o asset antigo disponível.

Novo HTML não reutiliza o cache da URL antiga. Chromium local confirmou a troca para o asset versionado por navegação normal, sem forçar atualização dos scripts, enquanto a URL antiga continuava em cache. O frontend novo funciona também com os handlers publicados.

Isso NÃO atualiza código já carregado em abas abertas nem HTML antigo que continue em cache. A política real de cache/CDN do frontend não foi consultada. Antes de trocar o backend: encerrar atividades administrativas, fechar/recarregar abas, obter HTML novo e confirmar em Network que o asset com hash foi entregue e os dois POST enviam Authorization. Se necessário, usar recarregamento forçado ou mecanismo de invalidação efetivamente suportado pelo serviço, a confirmar mediante autorização. Não presumir limpeza automática pelo deploy.

Consumidor antigo contra intermediário recebe 401 sem gravar: proteção correta, mas indisponibilidade funcional para aquela aba. Não reduzir autorização no backend para acomodar cache antigo. Se não houver procedimento verificável de atualização dos clientes administrativos, não avançar à troca do backend.

## Ordem futura — pontos de parada obrigatórios

Nenhuma das operações externas abaixo está autorizada nesta etapa.

1. **Revisão e preparação de ambiente.** Aprovar os patches e hashes; confirmar repositório/branch/root/build/output do frontend e Git SHA/start command/Python do backend, sem expor variáveis sensíveis. Confirmar que o backend continua manual e que o frontend realmente publica após push. Não usar o workspace principal para integração nem transportar seu diff integral.
2. **Integração A, só frontend.** Com autorização específica para commit/push, integrar exatamente frontend-primeiro.patch à base publicada, em checkout/branch isolado. Não incluir backend nem migração nesse primeiro commit. O push poderá publicar o frontend automaticamente; esse efeito deve estar autorizado antes de realizá-lo. Registrar SHA A e acompanhar o resultado do frontend. NÃO acionar deploy manual do backend nesse SHA.
3. **Verificação A contra backend publicado.** Confirmar HTML/asset com hash, sessão, Geral e as quatro operações na homologação. Em produção, não criar dados de teste por padrão; observar uma operação administrativa legítima autorizada ou validar previamente a mesma combinação em homologação. Preservar os fluxos existentes. Resolver cache/abas antigas antes da janela do backend. Se A falhar, não migrar: corrigir/republicar A sob autorização.
4. **Integração B e recuperação pronta.** Com autorização para o segundo commit/push, incorporar apenas as mudanças backend/testes auditadas, mantendo exatamente o frontend de A. Registrar SHA B seguro, artefato verificável, build e teste de recuperação disponíveis. Não disparar backend automaticamente. Se o frontend redeployar, seu conteúdo funcional é o mesmo de A. Um patch completo deve ser aplicado à base, não reaplicado cegamente sobre A; revisar apenas o delta backend restante.
5. **Backup e drenagem.** Obter autorização de produção, backup restaurável e plano de manutenção. Identificar TODOS os escritores/processos/jobs e caminhos externos. Uma instância não prova ausência de sobreposição. Entrar em manutenção por procedimento previamente ensaiado, interromper/drenar processos antigos e confirmar que não atendem/gravam. O servidor temporário de manutenção presente na base não encerra, por si, os outros escritores. Não executar NOLOGIN nem derrubar indiscriminadamente sessões do papel compartilhado postgres. Sem prova de drenagem, parar aqui.
6. **Pré-verificações de leitura.** Executar preflight022_leitura.sql somente quando autorizado. Registrar contagens após a drenagem, antes da migração. Os números históricos eram 60 usuários e cinco administradores ativos; não descartar cadastros legítimos posteriores para forçar esses números. Investigar divergências. Se coluna/auditoria já existirem, verificar tipos, constraints, FKs, defaults e permissões antes de reaplicar; IF NOT EXISTS não certifica schema. Se houver restritos inesperados, não promovê-los: revisar o plano.
7. **Migração 022.** Somente com autorização explícita, executar o arquivo integral, com BEGIN/COMMIT e timeouts preservados, em conexão administrativa adequada. Não executar por trechos nem automatizar no startup. Usar sessão sem transação pendente e interromper em erro. Não iniciar o novo modelo antes de confirmar o COMMIT.
8. **Verificação do banco.** Executar postflight022_leitura.sql. Comparar contagens com a captura anterior; todos os administradores legados devem ser Gerais, ativos conforme antes; zero combinações inválidas. Conferir vendedores/pagamentos/acessos, constraint e auditoria. Contagens não substituem backup nem prova de igualdade de todos os campos. A migração local foi homologada com preservação de valores e vínculos. Se houver divergência, manter manutenção e investigar.
9. **Backend B manual.** Implantar explicitamente o SHA B aprovado no serviço correto do Render. Não escolher HEAD, A ou cdba603 por conveniência. Confirmar processo/versão nova, startup, conexão esperada e /me dos Gerais, sem imprimir URL/segredos. Não habilitar restritos nem alterar credenciais. Conferir que não coexistem escritores antigos.
10. **Verificação e reabertura.** Validar saúde, login, restrição anônima das quatro rotas com payloads válidos (negação sem criar dados), Geral e auditoria em operação autorizada; confirmar frontend versionado e direitos próprios de aluno/vendedor. Não criar perfis restritos ou registros artificiais em produção. Após aprovação do operador, reabrir serviço e monitorar 401/403/5xx. Cache antigo deve ser corrigido no cliente, nunca pela retirada da guarda.

## Falha parcial e recuperação — somente intermediário seguro

- **Antes da 022:** interromper o avanço se frontend, cache, backup, drenagem ou build seguro não estiverem verificados. Não fazer migração para “testar se funciona”.
- **Erro/timeout antes do COMMIT:** a transação deve ser desfeita. Confirmar estado por leitura; resolver a causa e reaplicar o arquivo integral somente com autorização. Não iniciar o intermediário sem schema. Manter manutenção.
- **Resultado de COMMIT desconhecido:** não presumir sucesso nem rollback. Conferir coluna, constraint, tipos/dados e auditoria. A 022 é reaplicável no schema compatível, mas não usar isso para ignorar inconsistências.
- **022 concluída, backend falha:** manter schema e dados, não remover CHECK/coluna/auditoria. Recuperar exclusivamente com o mesmo pacote/SHA intermediário aprovado ou correção compatível autorizada. Não usar A nem cdba603. Se não houver build seguro disponível, manter manutenção; não reabrir pelo legado.
- **Processo cai antes do commit administrativo:** transação/locks são liberados e usuário/auditoria não persistem parcialmente, conforme ensaio PG. Após reinício, verificar saúde e estado antes de repetir uma operação; commit confirmado não é desfeito por falha na resposta.
- **Retorno a partir de futura versão completa:** este pacote reconhece false/admin_prod e false/admin_adm, mas lhes nega administração independentemente de flags. Preservar seus tipos e vínculos; nunca convertê-los em Gerais. Deve ser ensaiado novamente quando a versão completa/schema futuro forem definidos.

A restauração de backup inteiro não é um rollback automático: pode apagar operações legítimas posteriores. Exige procedimento próprio, diagnóstico, aprovação e critérios de perda de dados. Não há script destrutivo de reversão neste kit.

## Critérios de liberação e pendências

Pronto localmente: cache versionado, pacotes reproduzíveis e separados, verificação offline, patches por etapa e consultas exclusivamente de leitura. Testes adicionais estão nos logs de preparação/cache.

Ainda não comprovados: configuração real de publicação/cache, build/runtime recuperável no Render, Session Pooler real de homologação, backup restaurável, inventário/drenagem, restrição operacional de deploy/rollback e verificação dos SHAs futuros. Sem comprovar esses pontos não liberar produção. A ausência de Session Pooler isolado não foi contornada usando produção ou criando serviço pago.

Próximas autorizações devem separar: revisão/commit local; push com efeito de frontend automático; eventual homologação externa sem produção; e, por último, janela de produção, backup, migração e deploy manual. Não realizar nenhuma delas implicitamente.
