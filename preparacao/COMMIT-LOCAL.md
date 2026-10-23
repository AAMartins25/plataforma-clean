# Registro da preparação do commit local

O commit local autorizado reúne backend intermediário, frontend compatível com cache versionado, migração 022, testes e documentação. Sua base direta é cdba603e9a8d3a3a04a77fc03863ad41c93c1a93. Administradores restritos continuam sem competências administrativas.

Os relatórios anteriores registram etapas históricas sem commit. O roteiro propôs integração futura em dois commits; esta autorização posterior determina um único commit local completo. Qualquer publicação futura deverá ser novamente autorizada e planejada: um push deste commit pode publicar automaticamente o frontend, enquanto o backend permanece manual e só poderá ser implantado após a migração autorizada e as verificações do roteiro. Não executar implicitamente a proposta anterior de dois commits.

Logs, bancos, resultados de execução, patches e pacotes gerados permanecem fora do commit. O manifesto evidencias/manifesto.json é incluído por ser a lista de hashes das fontes auditadas exigida pelo construtor; evidencias/runner_sqlite.py é suporte reproduzível aos testes SQLite, sem alteração de negócio.

Para reconstruir os pacotes locais a partir das fontes, execute primeiro `python preparacao/construir_artefatos.py`. Depois, `python -m pytest preparacao/test_artefatos.py`. Esses comandos escrevem somente artefatos locais; não aplicam migrações nem acessam serviços externos. Os pacotes de fontes não substituem a homologação do runtime Render.

Continuam pendentes as verificações operacionais do roteiro: cache/publicação reais, build recuperável, backup restaurável, drenagem de processos e Session Pooler isolado. cdba603 não é recuperação segura após a migração 022.
