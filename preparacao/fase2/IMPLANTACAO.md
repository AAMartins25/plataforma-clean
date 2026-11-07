# Implantação autorizada futura

1. Preservar backup consistente do PostgreSQL de produção e registrar versão/artefatos
   atuais. Validar esquema e papel SQL das migrações 023/024: dependências existentes,
   ownership/permissões e RLS sem acesso público. Aplicar somente migrações pendentes
   após revisão, nunca copiar o banco ou os metadados fictícios da homologação.
2. Criar manualmente `teoria-imagens-producao` privado, com limite 5 MiB e MIME types
   PNG/JPEG/WebP, sem políticas públicas. Manter `teoria-imagens` e seus quatro objetos
   fictícios exclusivamente na homologação, sem remoções. Nenhum bucket é criado pelo código.
3. No backend de produção, configurar privadamente as variáveis de `producao.env.example`
   com URL do mesmo projeto e credencial própria. Preservar DATABASE_URL e SECRET_KEY
   de produção. Nunca publicar chave Supabase no frontend. Confirmar Python >=3.11,
   Pillow==13.0.0 e instalação das dependências; conferir capacidade e conexões totais
   (pool padrão 5 por worker, overflow 0) contra limite do banco.
4. Após autorização de publicação, integrar exclusivamente pelo checkout isolado,
   publicar backend compatível com o esquema e depois frontend. Validar upload,
   leitura autorizada e persistência com material controlado. Manter manutenção false.
5. Se houver falha, suspender novas importações/edições, preservar tabelas, vínculos,
   materiais e objetos. Reverter frontend se necessário, mantendo backend capaz de ler
   referências de imagens da Fase 2. Não reverter esquema nem restaurar backup antigo
   sobre dados novos sem reconciliação. Backup SQL não inclui os bytes no Storage.

A compensação só exclui uploads confirmados após rollback comprovado antes do commit.
Após tentativa de commit, preservar objetos mesmo em erro e reconciliar manualmente
com autorização. A manutenção automática exige homologação/autorização separada.
