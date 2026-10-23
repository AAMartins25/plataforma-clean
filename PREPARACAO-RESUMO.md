# Preparação local concluída — 23/10/2026

- Roteiro: ROTEIRO-IMPLANTACAO-INTERMEDIARIO.md.
- Cache: asset com hash em 18 páginas; novo HTML supera cache do JS antigo. Abas/HTML antigos ainda precisam ser atualizados pelo procedimento operacional.
- Pacotes e patches por etapa: artefatos/INDICE.json e SHA256SUMS. Frontend não contém backend; pacote de recuperação é byte a byte igual ao intermediário seguro.
- Verificador offline validado com SHA externo e finalidade. Recuperação recusada para pacote de frontend, adulteração e checksum incorreto.
- Sete testes de preparação passaram; ensaio Chromium do cache versionado passou. Patches conferidos em modo --reverse --check, sem aplicação. Nenhuma regressão ampla repetida.
- Backend auditado, migração e demais 12 arquivos originais permanecem com os hashes anteriores; principal preservado (6.979 arquivos).
- Pacotes são fontes, não imagem do runtime. requirements publicado está sem versões fixas; confirmar build/Python/dependências e recuperação executável no Render antes de produção, sem alterar dependências nesta preparação.
- Pendências: configurações reais/cache, SHAs após futura autorização de commit, runtime/build de recuperação, Session Pooler isolado, backup restaurável, drenagem/inventário e janela operacional.
- Próximas autorizações separadas: commit; push com deploy automático do frontend; eventual homologação externa; por último produção/migração/deploy manual. Nenhuma está presumida.

Nenhum commit, push, deploy, alteração persistente de banco, credencial ou serviço externo. Restritos bloqueados. Consultas SQL preparadas são apenas de leitura e não foram executadas.
