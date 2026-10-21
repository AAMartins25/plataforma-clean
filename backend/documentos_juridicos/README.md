# Documentos jurídicos recebidos — versões provisórias 1.0

Localização definitiva dos PDFs para o aluno: `site-html/juridico/`. Os arquivos deste pacote são cópias de preservação histórica com os mesmos hashes; os links nas páginas de compra apontam diretamente para a pasta definitiva no frontend.

Pacote incorporado exclusivamente na worktree isolada. Sem publicação, execução de SQL ou ativação.

`1.0/` contém:
- os dois PDFs originais, idênticos em bytes aos arquivos recebidos;
- os dois textos UTF-8 extraídos integralmente com pypdf 6.21.2, modo layout, sem edição jurídica;
- `manifesto.json`: hashes separados de PDF/texto, contagem de páginas e campos, identificação provisória e método de conferência;
- `documentos-1.0.sql`: dois INSERTs preparados para revisão, não executados, sem UPDATE da política de ativação.

Termos: 9 páginas, 6 campos `[A PREENCHER]`. Política: 10 páginas, 7 campos `[A PREENCHER]`. Ambos mantêm avisos de minuta. Todos os campos e avisos foram conservados. Nenhuma data de vigência, identificação empresarial ou contato foi preenchido.

A extração mantém também cabeçalhos/rodapés e separa páginas com `\n\f\n`. Não é uma reconstrução da diagramação. O PDF original é a referência visual integral, conservada em bytes. A conferência independente com PyMuPDF 2.0 concordou em todas as páginas ao ignorar apenas espaços e quebras de linha; nenhum caractere ilegível de substituição foi encontrado.

O pypdf informou que a tabela xref não começa em zero. Ambos os leitores abriram todas as páginas sem perda identificada; a correção foi apenas interna ao parser. Os PDFs não foram reparados nem regravados. As primeiras e últimas páginas também foram inspecionadas visualmente.

O registro da versão guarda SHA-256 do texto e do PDF. O aceite aponta para os IDs dessas versões, inclusive nas renovações. A consulta da versão permite recuperar o texto e abrir o PDF original por hash. O backend rejeita vínculos incompatíveis ou PDFs corrompidos antes de iniciar/reabrir preferência.

A exigência continua desabilitada por padrão e a política não é alterada pelo SQL de documentos. Qualquer inclusão em banco, ativação, integração ou publicação depende de autorização. Antes de publicação definitiva, permanecem a revisão jurídica e o preenchimento dos dados da futura pessoa jurídica, sempre em nova versão se a 1.0 já tiver sido aceita.

Para repetir a conferência, usar `evidencias/aceite/conferir-pdfs.py` com pypdf/PyMuPDF instalados separadamente. Essas bibliotecas não são dependências da aplicação. Conferir também o procedimento em `backend/migrations/021_aceites_juridicos.md`.
