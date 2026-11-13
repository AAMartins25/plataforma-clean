# Correção da seta e botão de acesso — 13/11/2026

Base: origin/main 5c0d2433f91e70a61debd912fb65075be9c9a4de. Worktree isolada; nenhuma alteração no backend, banco, Supabase ou Render.

## Diagnóstico e causa reproduzida

A consulta pública somente de leitura mostrou index.html e os quatro assets CSS/JS iguais à base origin/main (hashes e medidas em consulta-publica-antes.json). Uma navegação limpa já não exibia seta. Portanto, não foi possível comprovar o conteúdo do cache do navegador que apresentou o problema.

A combinação de HTML anterior (index.html de ce16507) com CSS atual reproduziu exatamente a regressão. O elemento responsável é svg.home-cursos-toggle-icon, viewBox="0 0 24 24", path="m6 9 6 6 6-6". O HTML antigo não tem width/height; a remoção das regras .home-cursos-toggle e .home-cursos-toggle-icon no último commit deixou o SVG dimensionar-se pela largura disponível, em proporção 1:1. O antigo contêiner deixou de ter display:flex e o SVG passou a ocupar uma linha inteira antes da lista. Esse é um defeito de compatibilidade entre versões de HTML/CSS, reproduzido; a permanência de HTML em cache no navegador afetado é a hipótese compatível com a consulta atual, não uma leitura daquele cache.

Medições da reprodução com um curso de teste e o mesmo HTML histórico antes/depois:

| Largura | Seta antes (px) | Altura seção antes (px) | Altura seção depois (px) |
| --- | --- | --- | --- |
| 320 | 262 × 262 | 414.39 | 144.80 |
| 390 | 332 × 332 | 492.34 | 152.75 |
| 768 | 674 × 674 | 867.03 | 185.44 |
| 1366 | 826 × 826 | 1019.03 | 185.44 |

## Correção

- CSS exclusivo da Home oculta o SVG legado antes da primeira pintura, inclusive com app.js pausado.
- Compatibilidade no app.js, limitada a body.home-page: remove o SVG do DOM, troca o wrapper legado pelo título estático, remove handlers/atributos de expansão e retira display inline do catálogo. O HTML novo já não contém controle ou função de expansão. Nenhuma altura fixa introduzida; paginação Mais/Menos cursos existente mantida.
- Removido texto visível do acesso. Botão circular de 50×50 px até 600 px e 52×52 px acima; ícone branco de 24×24 px. aria-label e title "Minha Área" preservados, assim como href e onclick. Texto legado também é ocultado/removido em HTML anterior.
- Fundo #789B45, hover/focus #708F40, active #68853B, borda #738F43. Contraste branco/fundo normal 3,19:1, atende 3:1 para ícone gráfico. Foco com contorno visível #536E33. Cor do nome Resumão #2E7D32 intacta.
- URLs dos assets específicos da Home atualizadas para CSS v7/app v5. Nenhuma mudança em CSS global.

## Verificações

- Chromium: página completa inspecionada em 320, 390, 768 e 1366 px; visitante e perfil autenticado controlado via /me. Oito capturas finais e medidas anexadas. Sem transbordamento, colisões ou seta; botão matematicamente centralizado no nome (<0,5 px), com ícone centralizado nos dois eixos.
- Posição superior da marca inalterada antes/depois: visitante 2 px em mobile e 4 px em tablet/desktop; identificado 19 px e 21 px. Posição vertical do botão também inalterada em todas as oito combinações; medidas completas anexadas.
- Regressão de HTML legado testada nas quatro larguras antes/depois do JS; seta com altura zero antes do JS e ausente do DOM depois; wrapper sem role, tabindex, aria-expanded, aria-controls, onclick ou onkeydown; lista visível inclusive quando HTML antigo possuía display:none.
- Catálogo com quatro/seis cursos, metadados completos/parciais/ausentes, texto longo, vazio/erro, escaping, pesquisa e navegação pelo cartão aprovados.
- Acesso visitante→login, aluno→cursos, admin→admin/index, duplo perfil→minha-area; voltar/sair, atendimento e limpeza dos contextos de compra preservados.
- 6 suítes Node de compras, meus cursos, sessão, autenticação tardia, retorno de pagamento e perfis aprovadas.
- 3 testes pytest aprovados, incluindo frontend Chromium consumindo resposta HTTP real da rota /cursos-publicos em app e banco SQLite isolados, nas oito combinações de largura/sessão. Sem alteração de dados de produção.
- Rodapé dinâmico Quality e 58 rodapés existentes continuam passando na validação. Logotipo, espaçamentos, slogan, cartões, Localizar curso, Atendimento e corrida preservados.

Os testes de perfis usam sessões controladas; não foi utilizado login de uma conta real de produção. Não foi feito deploy. O arquivo consulta-publica-antes.json registra assets públicos reais; cursos e perfil usados na medição dessa consulta foram controlados, sem credenciais reais.

## Arquivos de implementação

site-html/index.html; site-html/css/home-publica.css; site-html/js/app.js (bloco exclusivamente da Home); site-html/test-home-publica-browser.cjs. Esta pasta contém relatório, capturas e medições.
