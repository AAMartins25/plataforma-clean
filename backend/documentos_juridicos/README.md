# Documentos jurídicos recebidos — versões provisórias 1.0

Localização definitiva dos PDFs para o aluno: `site-html/juridico/`. Os arquivos deste pacote são cópias de preservação histórica com os mesmos hashes; os links nas páginas de compra apontam diretamente para a pasta definitiva no frontend.

Estado inicial da preparação: pacote incorporado em worktree isolada, sem publicação, execução de SQL ou ativação naquele momento.

`1.0/` contém:
- os dois PDFs originais, idênticos em bytes aos arquivos recebidos;
- os dois textos UTF-8 extraídos integralmente com pypdf 6.21.2, modo layout, sem edição jurídica;
- `manifesto.json`: hashes separados de PDF/texto, contagem de páginas e campos, identificação provisória e método de conferência;
- `documentos-1.0.sql`: dois INSERTs transacionais, sem UPDATE da política de ativação; a revisão de transporte usa Base64 para preservar os bytes aprovados.
- `conferir-importacao.sql`: SELECT independente para conferir as cargas e seus hashes, sem escrita no banco.

Termos: 9 páginas, 6 campos `[A PREENCHER]`. Política: 10 páginas, 7 campos `[A PREENCHER]`. Ambos mantêm avisos de minuta. Todos os campos e avisos foram conservados. Nenhuma data de vigência, identificação empresarial ou contato foi preenchido.

A extração mantém também cabeçalhos/rodapés e separa páginas com `\n\f\n`. Não é uma reconstrução da diagramação. O PDF original é a referência visual integral, conservada em bytes. A conferência independente com PyMuPDF 2.0 concordou em todas as páginas ao ignorar apenas espaços e quebras de linha; nenhum caractere ilegível de substituição foi encontrado.

O pypdf informou que a tabela xref não começa em zero. Ambos os leitores abriram todas as páginas sem perda identificada; a correção foi apenas interna ao parser. Os PDFs não foram reparados nem regravados. As primeiras e últimas páginas também foram inspecionadas visualmente.

O registro da versão guarda SHA-256 do texto e do PDF. O aceite aponta para os IDs dessas versões, inclusive nas renovações. A consulta da versão permite recuperar o texto e abrir o PDF original por hash. O backend rejeita vínculos incompatíveis ou PDFs corrompidos antes de iniciar/reabrir preferência.

A exigência continua desabilitada por padrão e a política não é alterada pelo SQL de documentos. Qualquer inclusão em banco, ativação, integração ou publicação depende de autorização. Antes de publicação definitiva, permanecem a revisão jurídica e o preenchimento dos dados da futura pessoa jurídica, sempre em nova versão se a 1.0 já tiver sido aceita.

Para repetir a conferência, usar `evidencias/aceite/conferir-pdfs.py` com pypdf/PyMuPDF instalados separadamente. Essas bibliotecas não são dependências da aplicação. Conferir também o procedimento em `backend/migrations/021_aceites_juridicos.md`.

## Importação sem perda de caracteres — revisão de transporte

O SQL antigo inseria o texto literalmente, inclusive LF, espaços e separadores
U+000C de páginas. O arquivo original passa na constraint PostgreSQL, mas copiar
o SQL achatando as linhas altera os bytes dos documentos. No SQL informado após
a falha de produção, as linhas dos textos foram substituídas por espaços, mantendo
os hashes originais. O COMMIT também ficou na mesma linha do comentário `--`.

O gerador agora transporta os bytes UTF-8 originais em Base64 ASCII, em blocos
concatenados explicitamente. `pg_catalog.decode` e `pg_catalog.convert_from`
reconstroem o texto exato no PostgreSQL. Base64 é apenas transporte, não criptografia
nem alteração documental. Nenhum PDF, texto aprovado, hash ou versão foi alterado.
A constraint `documento_hash_correto`, REVOKE, RLS e triggers permanecem ativos.
O comentário final usa `/* ... */`, para não ocultar COMMIT se as linhas forem
achatadas. O arquivo continua transacional e contém somente os dois INSERTs.

`1.0/conferir-importacao.sql` é um SELECT independente: reconstrói as mesmas cargas,
retorna tamanho UTF-8 e hashes esperado/calculado, sem consultar ou alterar tabelas.
Antes de nova tentativa autorizada, executar esse arquivo completo no SQL Editor
e conferir duas linhas com `confere=true`: TERMOS com 22416 bytes e PRIVACIDADE
com 22507 bytes. Conferir também que a tabela de documentos está vazia e a política
está desabilitada. Após autorização separada, executar `documentos-1.0.sql` completo,
sem editar suas cargas, e conferir os hashes armazenados e a política novamente.
Não reexecutar a migração 021 nem tentar remover/recriar a constraint.
Em caso de falha, confirmar encerramento/rollback da tentativa anterior e consultar
os registros antes de qualquer repetição. Não sobrescrever versões persistidas.

O gerador aceita `--conferencia caminho.sql` para gerar o SELECT junto do arquivo
de importação; os arquivos de saída usam modo exclusivo para evitar sobrescrita
acidental. Os textos UTF-8 e PDFs arquivados continuam sendo os documentos legíveis.

Testes: `backend/test_importacao_juridica_transporte_pg.py`, com o mesmo opt-in
local da suíte `test_migracao021_seguranca_pg.py`. Incluem SQL original/CRLF/linha
única/remoção de espaços finais, causa reproduzida nos dois documentos, corrupção
da segunda carga com rollback integral e fixtures de Unicode/caracteres de controle.
Nenhum desses testes se conecta ao Supabase ou utiliza Mercado Pago real.

Confirmação operacional informada pelo responsável em 22/10/2026: importação corrigida dos dois documentos concluída no Supabase de produção, com hashes conferidos e política habilitada=false. Esta publicação registra a correção no repositório; não exige nova importação nem reexecução da migração. As instruções de nova tentativa acima aplicam-se somente a um destino vazio e mediante autorização.
