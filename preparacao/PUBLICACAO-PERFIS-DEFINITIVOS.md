# Pacotes definitivos dos perfis administrativos

Esta preparação substitui, para os três perfis, o empacotamento intermediário 022. Não publica nada e não executa migrações. Os documentos antigos de implantação do intermediário são históricos; suas instruções de migração e de restritos sem competências não se aplicam a esta versão.

A matriz é preservada: Geral possui todas as funcionalidades administrativas e exclusividade para gerir perfis e Comercial; Produção possui Criar Curso e Questões, com operações internas; Administrativo possui Pagamentos, Atendimento e Mensagens de questões, com operações internas. Restritos mantêm `is_admin=false`.

## Evidência de compatibilidade do banco

O usuário confirmou nesta conversa que as sete consultas de diagnóstico já executadas no Supabase comprovaram a estrutura pós-022 e os cinco Administradores Gerais. Essa confirmação foi registrada em `evidencias/diagnostico-pos022-confirmado.json`. Não foram repetidas consultas. O registro identifica sua origem e não pretende substituir ou inventar os resultados brutos.

Essa estrutura atende ao código existente: `usuarios.tipo_admin`, constraint `ck_usuarios_tipo_admin`, `auditoria_perfis_admin` e Gerais classificados. Nenhuma nova migração é necessária para esta implementação. A presença dos arquivos SQL históricos no pacote de fontes não significa autorização para executá-los.

## Fontes e integridade

`evidencias/manifesto.json` fixa os hashes de todas as fontes incluídas, a base Git completa e a matriz definitiva. O manifesto não inclui seu próprio hash para evitar autorreferência; seu hash é registrado em cada manifesto de release. O manifesto anterior foi preservado em `evidencias/manifesto-intermediario-022.json`.

O construtor usa exclusivamente os caminhos e hashes fixados; não empacota automaticamente arquivos não rastreados, segredos, logs, bancos, caches ou o diretório de artefatos. Rejeita fonte divergente, omissão de arquivo da base e dependência estática ausente. Não importa a aplicação nem usa conexão de banco.

Os pacotes anteriores foram preservados em `artefatos/historico-intermediario-022/`. Somente os nomes novos listados em `artefatos/INDICE.json` representam esta implementação:

- `frontend-perfis-definitivos.tar.gz`: conteúdo de `site-html/`, permitido somente para frontend.
- `backend-perfis-definitivos.tar.gz`: fontes completas, com backend, frontend, testes, documentação e evidências, permitido para backend e recuperação compatível.
- `recuperacao-perfis-definitivos.tar.gz`: cópia idêntica do pacote backend definitivo. Recupera o mesmo código compatível com pós-022; não desfaz schema nem representa backup/restauração de dados.

Cada pacote contém `RELEASE-MANIFEST.json` com matriz, flags, hashes, árvore do frontend, base de fontes e `restritos_habilitados=true`. O verificador rejeita os pacotes intermediários como versão definitiva, uso incorreto, adulteração, entradas inseguras e módulos obrigatórios ausentes.

Os dois patches são relativos ao commit `base_sha` fixado no índice. São auxiliares de revisão/aplicação local; não substituem os pacotes completos. Nenhum commit foi criado. Os identificadores do release derivam dos hashes do conteúdo, não de um suposto commit da implementação.

## Comandos locais

Na raiz do repositório:

```sh
python preparacao/construir_artefatos.py
python -m pytest preparacao/test_artefatos.py
(cd artefatos && sha256sum --check SHA256SUMS)
```

Para verificar um pacote individual, use o SHA-256 correspondente de `INDICE.json`:

```sh
python preparacao/verificar_artefato.py artefatos/backend-perfis-definitivos.tar.gz --sha256 SHA256_DO_INDICE --uso backend
python preparacao/verificar_artefato.py artefatos/recuperacao-perfis-definitivos.tar.gz --sha256 SHA256_DO_INDICE --uso recuperacao
python preparacao/verificar_artefato.py artefatos/frontend-perfis-definitivos.tar.gz --sha256 SHA256_DO_INDICE --uso frontend
```

SHA-256 comprova integridade em relação ao digest confiável distribuído separadamente; não é assinatura digital. A matriz no manifesto descreve a implementação já homologada; testes de pacote não substituem testes funcionais, cujas evidências foram preservadas.

## Publicação futura

Pacotes verificados ficam prontos para a publicação autorizada. Continuam dependentes de autorização posterior: commit, push, deploy e quaisquer alterações no Render ou em produção.

A atualização deve coordenar backend e frontend: o frontend definitivo chama endpoints novos e precisa do backend definitivo. Depois, conferir o código efetivamente servido e a chave de cache `perfis-1`, mantendo uma cópia íntegra dos pacotes e hashes para recuperação. Essa conferência operacional não foi executada nesta preparação.
