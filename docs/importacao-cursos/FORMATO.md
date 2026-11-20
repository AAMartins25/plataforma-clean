# Importação de curso completo — versão 1

O arquivo é JSON UTF-8, sem comentários, com `versao` igual ao inteiro `1`, `curso` e `disciplinas`. Não são aceitos campos adicionais em nenhum objeto. A posição dos elementos nos arrays define a ordem no curso. IDs, preços, publicação, vídeos, imagens e questões práticas avulsas não fazem parte do formato. O arquivo de exemplo é `exemplo-v1.json`.

Todos os campos listados abaixo são obrigatórios. Textos não podem conter apenas espaços. Os títulos e nomes têm no máximo 255 caracteres; cada campo Markdown tem no máximo 250.000 caracteres. Cada assunto aceita até 20 resumos e 20 baterias. O conjunto aceita até 10.000 assuntos. Não há mínimo de disciplinas, assuntos, resumos ou baterias. A interface aceita arquivos de até 40 MiB; a solicitação ao servidor, contendo original e conteúdo convertido, tem limite de 128 MiB. O conversor existente também limita a complexidade de cada campo Markdown e pode emitir avisos.

- `curso`: `nome`, `banca`, `cargo`, `orgao`, `ano`, `uf`, `descricao_publica_markdown`. O ano é inteiro entre 1000 e 9999 e a UF é uma das 27 siglas brasileiras em maiúsculas.
- Cada elemento de `disciplinas`: `nome` e array `assuntos`.
- Cada assunto: `nome`, `aula_titulo`, arrays `resumos` e `baterias`.
- Cada resumo: `titulo`, `texto_markdown`.
- Cada bateria: `titulo`, `tipo` (`MULTIPLA` ou `CERTO_ERRADO`) e array `questoes` com exatamente dez elementos.
- Cada questão: `tipo`, `enunciado_markdown`, objeto `alternativas`, `gabarito`, `comentario_markdown`. Para `MULTIPLA_4`, as chaves são exatamente `A`, `B`, `C`, `D` e o gabarito é uma delas; para `MULTIPLA_5`, acrescente `E`. Uma bateria `MULTIPLA` aceita ambos os tipos. Para `CERTO_ERRADO`, o objeto de alternativas é vazio e o gabarito é `C` ou `E`. Questões de certo/errado não podem ser misturadas com múltipla escolha na mesma bateria.

A interface converte Markdown com o mesmo conversor e normaliza o HTML com o CKEditor antes de enviar o original e o HTML ao servidor; os sanitizadores existentes são aplicados novamente no servidor. A importação requer que o CKEditor e sua licença estejam disponíveis, como no cadastro manual. Na descrição pública, links e fórmulas são rejeitados conforme as regras do botão manual. Imagens em Markdown ou HTML são rejeitadas. Recursos não suportados pelo conversor podem gerar avisos. O curso é criado não publicado com valores provisórios positivos de R$ 0,04, R$ 0,08 e R$ 0,12. Para liberar publicação e aquisição, informe valores definitivos diferentes dos valores atuais nos três períodos e marque a confirmação explícita ao salvar.

A chave de idempotência gerada pela interface fica armazenada no navegador por hash do arquivo: repetir a mesma solicitação recupera o curso criado, enquanto reutilizar a chave com conteúdo diferente produz conflito. O servidor cria a árvore e registra a chave na mesma transação. Uma pasta TEORIA e uma aula técnica são criadas por assunto.
