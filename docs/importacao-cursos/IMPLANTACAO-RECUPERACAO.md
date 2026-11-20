# Implantação e recuperação da importação

Este procedimento é uma preparação: não configura o Render, não aplica migrações e não substitui a conferência do esquema real. A liberação exige backup restaurável, aprovação operacional e verificação de todas as instâncias e regras de borda.

## Cache e abas abertas

Os HTMLs que usam `app.js`, `admin.js`, `admin-criar-curso-completo.js` e `admin-importar-curso.js` referenciam `v=importacao-20261120-1`. Alterar a versão quando o conteúdo de qualquer um deles voltar a mudar. Em cada publicação, configurar no serviço estático Render cabeçalhos `Cache-Control: no-store` para HTML, incluindo `/`, `/*.html`, `/admin/*.html` e qualquer rota alternativa que entregue HTML. Conferir conflitos com regras existentes e `CDN-Cache-Control`, inclusive nas rotas reais e nos domínios usados. Não presumir que um arquivo `_headers` é aplicado pelo Render.

Antes de reabrir o tráfego, conferir pelo HTTP real do ambiente autorizado o HTML, o cabeçalho e a versão dos scripts; verificar o cache do navegador e do CDN. O versionamento não altera código já carregado em abas abertas: avisar os usuários administrativos para concluir ou abandonar suas edições com segurança, fechar/recarregar as abas durante a janela e verificar o frontend novo. Não forçar recarga automática que possa apagar respostas ou edições não salvas. Durante a convivência de versões, manter as operações afetadas bloqueadas; a autorização e as regras comerciais continuam sendo verificadas pelo backend.

## Versão de recuperação

A candidata é uma cópia imutável **desta versão completa do backend**, preparada e identificada antes da implantação, com as migrações 028–031 já aplicadas. Ela conserva os bloqueios de preços provisórios, venda desativada, idempotência administrativa, direitos e processamento financeiro. Uma versão-base anterior não é uma reversão segura. O modo de recuperação é habilitado no processo com `RESUMAO_RECUPERACAO_IMPORTACAO=1`; `0` ou ausência mantém o comportamento normal, e qualquer outro valor impede a inicialização. Fixar o identificador e checksum do pacote testado, dependências e configuração; repetir a validação caso qualquer conteúdo mude. O pacote ainda precisa ser construído e identificado na integração autorizada.

O modo bloqueia na entrada as rotas de importação/validação, duplicação integral, confirmação de preços/configuração pública, publicação, novo checkout e concessão/renovação administrativa. Responde 503 com `Retry-After`. Não bloqueia webhook nem confirmação de pagamentos iniciados anteriormente; não altera contratos ou acessos. A verificação de assinatura, idempotência e demais regras financeiras existentes permanece ativa. O modo é por processo e não garante drenagem das transações ou instâncias anteriores.

## Reversão operacional

1. Antes de trocar versões, bloquear na borda **todas** as rotas mencionadas acima e drenar requisições em curso em todas as instâncias; confirmar que não há bypass para o backend. Manter livres as rotas de notificação e confirmação financeira. Se não for possível garantir a drenagem ou o bloqueio de borda, não prosseguir com a troca.
2. Se houver incerteza financeira, usar o controle financeiro existente para `PAUSADO` e confirmar a drenagem. Webhooks assinados continuam registrados na caixa de entrada, mas seu processamento e a confirmação serão adiados. Nunca remover ou reconhecer manualmente notificações sem persistência.
3. Implantar a candidata imutável com `RESUMAO_RECUPERACAO_IMPORTACAO=1`; verificar a versão e a barreira em cada instância antes de retirar qualquer bloqueio de borda. Nunca implantar o backend-base que não conhece os preços provisórios. Preservar o banco e as quatro migrações; não restaurar backup integral como rollback normal.
4. Verificar leituras e direitos existentes. Confirmar que novos checkouts, concessões, importações e publicações falham; confirmar que webhooks válidos chegam e pagamentos anteriores podem ser processados. Se houver pausa financeira, usar o fluxo existente de `RECUPERACAO`, reconciliar com o provedor, processar pendências e somente então voltar a `NORMAL`. Não bloquear nem modificar acessos por reembolso ou contestação fora das regras manuais existentes.
5. Para voltar ao serviço normal, publicar uma versão corrigida e validada compatível com 028–031, drenar e conferir todas as instâncias, reconciliar os pagamentos, desativar o modo de recuperação e retirar os bloqueios de borda apenas após verificação. Uma falha incerta mantém as barreiras ativas.

## Seleção do pacote

Incluir os arquivos modificados e novos necessários da worktree, após revisão final:

- Backend funcional: `backend/app/{copias,cursos_comerciais,desempenho,financeiro_transacional,main,models,revisoes,schemas,disponibilidade_demonstracao,importacao_cursos,importacao_esquemas,recuperacao_importacao}.py` e suas dependências já existentes.
- Migrações e instruções: `backend/migrations/028_importacao_cursos.sql`, `029_referencia_preco_provisorio.sql`, `030_modalidade_demonstracao.sql`, `030_modalidade_demonstracao.md`, `031_idempotencia_acesso_admin.sql` e `031_idempotencia_acesso_admin.md`.
- Frontend: os HTMLs versionados, os scripts alterados `site-html/js/{app,admin,admin-criar-curso-completo,admin-importar-curso}.js`, `site-html/teoria.html` e `site-html/checkout.html`; manter os recursos existentes do CKEditor, Markdown e conteúdo rico.
- Testes alterados e novos de importação, comércio, demonstração, desempenho, revisões, pagamento, idempotência, cache e recuperação, inclusive a fixture PostgreSQL `test_cursos_comerciais_concorrencia_pg.py`; incluir `docs/importacao-cursos/`.

Excluir `.homologacao-*`, dumps, bancos, `.env`, segredos, licenças, diretórios de runtime, caches e arquivos temporários. Os backups existentes permanecem protegidos no ambiente de homologação, separados do artefato implantável. Antes da integração, inspecionar a lista explícita de arquivos, conteúdo e dependências; não utilizar inclusão indiscriminada da worktree.
