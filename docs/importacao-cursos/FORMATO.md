# Importação de curso completo — versão 1

O arquivo é JSON UTF-8, sem comentários, com `versao` igual ao inteiro `1`, `curso` e `disciplinas`. Não são aceitos campos adicionais em nenhum objeto. A posição dos elementos nos arrays define a ordem no curso. IDs, preços, publicação, vídeos e questões práticas avulsas não fazem parte do formato. O arquivo de exemplo é `exemplo-v1.json`. Um ZIP pode incluir imagens referenciadas nos campos de conteúdo, conforme a seção abaixo; o JSON isolado continua sem aceitar imagens.

Todos os campos listados abaixo são obrigatórios. Textos não podem conter apenas espaços. Os títulos e nomes têm no máximo 255 caracteres; cada campo Markdown tem no máximo 250.000 caracteres. Cada assunto aceita até 20 resumos e 20 baterias. O conjunto aceita até 10.000 assuntos. Não há mínimo de disciplinas, assuntos, resumos ou baterias. A interface aceita arquivos de até 40 MiB; a solicitação ao servidor, contendo original e conteúdo convertido, tem limite de 128 MiB. O conversor existente também limita a complexidade de cada campo Markdown e pode emitir avisos.

- `curso`: `nome`, `banca`, `cargo`, `orgao`, `ano`, `uf`, `descricao_publica_markdown`. O ano é inteiro entre 1000 e 9999 e a UF é `NACIONAL` ou uma das 27 siglas brasileiras em maiúsculas. Por exemplo, use `"uf": "NACIONAL"` para um curso de abrangência nacional. O mesmo contrato versão 1 se aplica a JSON e ZIP.
- Cada elemento de `disciplinas`: `nome` e array `assuntos`.
- Cada assunto: `nome`, `aula_titulo`, arrays `resumos` e `baterias`.
- Cada resumo: `titulo`, `texto_markdown`.
- Cada bateria: `titulo`, `tipo` (`MULTIPLA` ou `CERTO_ERRADO`) e array `questoes` com exatamente dez elementos.
- Cada questão: `tipo`, `enunciado_markdown`, objeto `alternativas`, `gabarito`, `comentario_markdown`. Para `MULTIPLA_4`, as chaves são exatamente `A`, `B`, `C`, `D` e o gabarito é uma delas; para `MULTIPLA_5`, acrescente `E`. Uma bateria `MULTIPLA` aceita ambos os tipos. Para `CERTO_ERRADO`, o objeto de alternativas é vazio e o gabarito é `C` ou `E`. Questões de certo/errado não podem ser misturadas com múltipla escolha na mesma bateria.

A interface converte Markdown com o mesmo conversor e normaliza o HTML com o CKEditor antes de enviar o conteúdo convertido ao servidor; os sanitizadores existentes são aplicados novamente no servidor. A importação requer que o CKEditor e sua licença estejam disponíveis, como no cadastro manual. Na descrição pública, links, fórmulas e imagens são rejeitados conforme as regras do botão manual. Recursos não suportados pelo conversor podem gerar avisos. O curso é criado não publicado com valores provisórios positivos de R$ 0,04, R$ 0,08 e R$ 0,12. Para liberar publicação e aquisição, informe valores definitivos diferentes dos valores atuais nos três períodos e marque a confirmação explícita ao salvar.

## Formatação dos resumos e questões

Em `texto_markdown`, `enunciado_markdown`, textos de `alternativas` e `comentario_markdown`, tanto no JSON como no ZIP, use `**negrito**` ou `__negrito__`, `*itálico*` ou `_itálico_`, e `<u>sublinhado</u>`. Para combinar estilos, por exemplo: `**<u>negrito e sublinhado</u>**`, `*<u>itálico e sublinhado</u>*` e `***<u>os três estilos</u>***`. O sublinhado usa exatamente `<u>` e `</u>`, sem atributos; marcadores incompletos ou vazios permanecem literais. Não aninhe sublinhados entre si. Crases e escapes preservam o texto literal conforme as regras Markdown.

Essa é uma extensão restrita: HTML arbitrário não é interpretado. A descrição pública mantém suas regras anteriores e não interpreta `<u>` como formatação. Revise o resultado no ADM antes da publicação.

A chave de idempotência gerada pela interface fica armazenada no navegador por hash do arquivo: repetir a mesma solicitação recupera o curso criado, enquanto reutilizar a chave com conteúdo diferente produz conflito. O servidor cria a árvore e registra a chave na mesma transação. Uma pasta TEORIA e uma aula técnica são criadas por assunto.

## Pacote ZIP com imagens

O mesmo botão aceita um ZIP com `curso.json` na raiz e imagens diretamente em `imagens/`:

```text
curso.zip
├── curso.json
└── imagens/
    ├── organograma.png
    └── grafico-01.webp
```

Há um exemplo completo em `exemplo-zip/curso.json` e `exemplo-zip/imagens/quadro.png`. Para experimentá-lo, compacte **o conteúdo** de `exemplo-zip/`, preservando `curso.json` na raiz do ZIP; não compacte a pasta externa como diretório adicional. O desenho é apenas ilustrativo.

`curso.json` segue integralmente a estrutura acima. Em `texto_markdown`, `enunciado_markdown`, textos de `alternativas` e `comentario_markdown`, use a sintaxe exata `![Descrição acessível](imagens/organograma.png)`. O nome deve coincidir exatamente com o arquivo, incluindo maiúsculas e minúsculas, e conter apenas letras ASCII, números, hífen e sublinhado, além da extensão `.png`, `.jpg`, `.jpeg` ou `.webp`. Não use espaços, subpastas, URLs remotas, HTML de imagem, dados incorporados, referências Markdown indiretas, títulos opcionais ou caminhos percentualmente codificados. A descrição pública continua sem aceitar imagens.

Todas as imagens incluídas precisam ser referenciadas e cada referência deve apontar para um arquivo do pacote. A mesma imagem pode ser usada em vários campos. As imagens são normalizadas e guardadas em armazenamento privado; referências em campos diferentes criam os vínculos adequados. Cada campo conserva o limite de 20 imagens do editor; o curso completo não tem esse limite, mas o pacote aceita até 100 arquivos de imagem. São aceitos até 64 MiB de ZIP, 128 MiB descompactados no total, 40 MiB de JSON e 5 MiB por imagem, além das restrições de dimensões da plataforma. ZIPs criptografados, links, arquivos especiais, nomes ambíguos e taxas de descompactação excessivas são recusados.

Para o GPT Work, produza `curso.json` válido e completo, gere os arquivos de imagem reais nos caminhos referenciados e compacte-os nessa estrutura. Não inclua imagens não utilizadas nem IDs ou URLs assinadas da plataforma. Revise o texto alternativo, o conteúdo das imagens, os gabaritos e a formatação; validação técnica não substitui revisão editorial.

A interface converte o Markdown e verifica a preservação das imagens no editor. O servidor valida novamente o ZIP, as referências e o HTML antes de gravar. Em falhas com resultado incerto, objetos remotos podem permanecer temporariamente para reconciliação. Repita o mesmo arquivo no mesmo navegador para recuperar uma importação já concluída. Preços provisórios, publicação e direitos permanecem iguais aos do JSON.
