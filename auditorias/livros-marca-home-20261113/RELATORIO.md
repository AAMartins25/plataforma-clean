# Livros e marca da Home — 13/11/2026

Base origin/main: 069d57d0c5534bd5df92f4c4a5549e6494d138df. Execução em worktree isolada.

- Livro do cabeçalho: contornos #2E7D32; check #D99C00. Variante book-check-header.svg, com geometria idêntica ao SVG original.
- Marca: removido o espaço literal entre os spans de Resumão e Online. Apresentação ResumãoOnline; nenhuma alteração de CSS, fonte, tamanho ou peso.
- Livro dos cursos: contornos #17365D; check original #F5B900 preservado. Variante book-check-course.svg, geometria idêntica ao original. Tamanhos reduzidos anteriores preservados.
- SVG original preservado. Novo endereço dos assets evita reutilização do SVG de outra cor em cache. Referência app.js na Home atualizada para v6.

## Validação

Chromium em 320, 390, 768 e 1366 px, visitante e perfil identificado controlado. Oito páginas completas inspecionadas visualmente, sem sobreposição ou transbordamento horizontal. Cores verificadas nos pixels renderizados de cada SVG por canvas, além das cores computadas da marca. Livros com dimensões anteriores; caminhos, transformações, viewBox e desenho iguais ao original, alteradas somente as cores.

Texto da marca exatamente ResumãoOnline; distância entre spans zero. Slogan e botão centralizados no nome com diferença inferior a 0,5 px. Botão oliva, área clicável e todos os estados preservados; coordenadas e dimensões do botão iguais às medições de referência. Posição vertical e altura da marca, navegação e padding preservados. Altura do cabeçalho conferida com o diagnóstico anterior e permaneceu idêntica nas oito combinações: 144,25/221,25 px em 320; 144,25/207,25 px em 390; 173,5/190,5 px em 768; 181,53125/198,53125 px em 1366 (visitante/identificado).

Teste completo da Home aprovado: cores renderizadas, alinhamentos, ausência de controles de expansão atuais e legados, vários cursos e paginação, metadados completos/parciais/ausentes, nomes longos, pesquisa, clique nos cartões, destinos de acesso de visitante/aluno/admin/duplo perfil, voltar/sair, atendimento, vazio/erro e rodapés dinâmicos. APIs e sessões controladas; não foi utilizado login de produção.

6 suítes Node aprovadas: compras, meus cursos, sessão, autenticação tardia, retorno de pagamento e perfis de acesso. Validade XML dos dois SVGs e identidade geométrica verificadas. git diff --check aprovado.

Nenhum CSS, backend, banco, registro de curso, checkout ou pagamento foi alterado. Sem deploy no Render ou alterações no Supabase. Workspace original e main local preservados.

## Arquivos

site-html/index.html; site-html/js/app.js (somente referência do SVG no cartão); site-html/assets/book-check-header.svg; site-html/assets/book-check-course.svg; site-html/test-home-publica-browser.cjs; esta pasta com evidências.
