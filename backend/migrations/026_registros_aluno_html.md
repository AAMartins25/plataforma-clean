# Formato de anotações e mensagens

Migração aditiva preparada, não executada em produção: `026_registros_aluno_html.sql`.

Adiciona `texto_formato` às tabelas `anotacoes_aluno_questao` e
`mensagens_conversa_questao`. O padrão é `texto_puro`; não altera os textos,
vínculos, identificadores, datas, permissões ou conversas existentes.
O formato `html_v1` identifica explicitamente somente conteúdo formatado novo
ou editado pelo usuário. Nunca inferir HTML a partir dos caracteres de um texto antigo.

Ordem de futura implantação: migração revisada e backup pelo procedimento
habitual; backend; frontend. A migração é idempotente e pode preceder o backend
antigo, que continua gravando texto simples com o padrão do banco.
Não disponibilizar o frontend novo antes do backend novo, pois versões antigas
não conhecem o discriminador de formato. Após haver registros HTML, não remover
a coluna em rollback: ela é necessária para interpretá-los sem perda.

O backend sanitiza o conteúdo ao gravar e ao retornar HTML, preserva o limite
de 300 palavras do texto visível e rejeita imagens. O navegador aplica sua
allowlist antes de inserir conteúdo no DOM e usa KaTeX existente para fórmulas.
Os registros antigos continuam sendo escapados e apresentados literalmente.
Se a CDN não carregar, texto antigo pode continuar sendo editado em texto simples;
um registro HTML fica protegido contra salvamento com perda de formatação.
O backend também rejeita a redução de uma anotação HTML para texto simples por
um cliente antigo.

A chave já configurada em `CKEDITOR_LICENSE_KEY` continua sendo necessária.
O endpoint `/me/ckeditor-chave` exige a autenticação existente. As operações de
anotação e conversa continuam fazendo as mesmas verificações de aluno, curso,
tentativa, questão, contexto e vigência. Nenhuma chave de servidor adicional é criada.

Validação executada com SQLite descartável e CKEditor 49.1.0 real. O SQL está
preparado para PostgreSQL; não houve aplicação em banco PostgreSQL nesta etapa.

## Revisão PostgreSQL/Supabase

Compatibilidade conferida contra os modelos locais, as migrações 011, 012, 020
e 025 e a documentação oficial de PostgreSQL e Supabase. Não houve conexão ao
banco de produção, consulta ao seu catálogo nem execução deste SQL, mesmo local.
Consequentemente, a revisão confirma a estrutura esperada pelo repositório,
sem certificar divergências eventualmente existentes na instância real.

O SQL definitivo fixa `public` nas duas tabelas, limita a espera por bloqueios
a 3 segundos e cada comando a 30 segundos, com configurações restritas à transação.
`ALTER TABLE` precisa de bloqueio exclusivo temporário: se não obtiver o bloqueio
no prazo, a execução falha, sem alterações parciais confirmadas. Executar sempre
o script inteiro e verificar o sucesso do COMMIT. Se houver erro, não implantar
o backend; se o editor mantiver a transação aberta/abortada, encerrá-la com ROLLBACK
antes de tentar novamente em uma nova execução.

Além de `IF NOT EXISTS`, há validação de tipo, tamanho, nulabilidade, ausência de
geração/identidade e valor padrão. Se uma coluna já existir com definição diferente,
inclusive um padrão equivalente escrito de outra forma, o script aborta de modo
conservador; não muda tipo, padrão ou registros automaticamente. A reexecução de uma
aplicação bem-sucedida apenas confirma a definição e preserva inclusive valores
`html_v1` ou NULL já existentes.

Não há UPDATE, DELETE, TRUNCATE, DROP, alteração de chaves, índices, sequências,
triggers de linhas, políticas RLS ou permissões. A adição fornece `texto_puro` para
os registros anteriores quando a coluna é criada, sem reinterpretar seu conteúdo.
Em PostgreSQL moderno, o padrão constante é mantido em metadados, sem reescrever
as linhas. Se a coluna já existia, seus valores NULL permanecem NULL e o backend
novo os trata como texto simples.

### Ordem segura de implantação manual

1. Executar integralmente `026_registros_aluno_html.sql` no SQL Editor do Supabase,
   com papel autorizado a alterar as duas tabelas; confirmar sucesso da transação.
2. Implantar o backend novo e aguardar a conclusão da troca de todas as instâncias.
   Conferir as rotas de anotações e mensagens antes de liberar o frontend novo.
3. Implantar o frontend novo.

Migração antes do backend é compatível com o backend antigo: as colunas são aditivas
e os INSERTs antigos usam o padrão. Backend novo antes da migração pode causar
`UndefinedColumn` nas consultas e gravações dessas entidades. Frontend novo antes
da conclusão da implantação do backend pode enviar HTML a uma instância antiga,
que desconhece o discriminador de formato; por isso essa ordem não é segura.

Após haver HTML gravado, um rollback para backend/frontend antigos não garante
a interpretação da formatação nem a proteção contra edição por clientes antigos.
Preservar as colunas e seus valores; preferir correção progressiva.

Referências oficiais:
- https://www.postgresql.org/docs/17/sql-altertable.html
- https://www.postgresql.org/docs/17/runtime-config-client.html
- https://supabase.com/docs/guides/database/tables

## Situação da migração na integração

A migração 026 foi aplicada e validada manualmente no Supabase de produção pelo
responsável, conforme confirmação recebida antes da integração do código.
Resultado informado: `Success. No rows returned`; estrutura correta nas duas
colunas, com 38 anotações e 29 mensagens, todas em `texto_puro`, sem valores
nulos, inesperados ou `html_v1` nessa verificação. Não houve acesso ao banco
por esta integração e o SQL não foi executado novamente.

A implantação pendente é: backend primeiro, aguardar a atualização completa de
todas as instâncias, depois frontend. A migração incluída no histórico não deve
ser reaplicada nesse banco de produção.
