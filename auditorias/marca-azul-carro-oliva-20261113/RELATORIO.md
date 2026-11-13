# Marca azul, slogan e carro — 13/11/2026

Base origin/main: f3bf490b85d93131ad33736ea7f6dc66534b14a4. Worktree isolada.

## Alterações

1. Resumão: fundo retangular permanente #245BD6, letras #FFFFFF, padding exclusivamente horizontal 0.045em. Fonte, peso e tamanho preservados, sem seleção de texto. Online permanece #D99C00 e sem fundo, imediatamente ao lado, sem espaço ou quebra.
2. Slogan: somente cor alterada para #789B45; tamanho, peso, espaçamento e centralização preservados. Botão circular não foi modificado.
3. Carro: carroceria e aerofólio em #789B45; detalhes prateados #C0C0C0 e #D9DDE1; acabamento cinza #69737D e contorno oliva #536E33. Apenas valores de cor do SVG alterados. Comparação geométrica com a base aprovada: desenho e demais atributos idênticos; bandeira byte a byte idêntica. Rodas, cockpit e traços de velocidade intactos. CSS de dimensões, posicionamento e animação inalterado.

## Validação

Chromium nas larguras 320, 390, 768 e 1366 px, visitante e perfil identificado controlado. Oito capturas completas inspecionadas. Cores computadas confirmadas; fundo permanente com seleção vazia; spans adjacentes sem espaço. Slogan e botão centralizados em relação ao nome com tolerância inferior a 0,5 px. Livros verde/dourado e marinho/dourado permanecem nas cores anteriores, verificadas por pixels renderizados.

Comparação com medições da base: mesma altura total do cabeçalho nas oito combinações, mesma posição superior e altura da marca, mesma posição vertical do botão e mesmos retângulos da navegação. Dimensões dos livros e botão inalteradas. Sem sobreposição ou transbordamento horizontal.

Teste completo de Home aprovado: cores/alinhamentos, catálogo permanente, compatibilidade com HTML legado, metadados completos/parciais/ausentes, pesquisa, seleção e navegação pelo cartão, destinos do acesso conforme visitante/aluno/admin/duplo perfil, voltar/sair, atendimento, estados vazio/erro e rodapé dinâmico Quality.

6 suítes Node aprovadas: compras, meus cursos, sessão, autenticação tardia, retorno de pagamento e perfis de acesso. git diff --check aprovado. Perfis e APIs controlados nos testes; nenhum login de produção ou transação real utilizado.

## Escopo

Implementação somente em site-html/index.html (cores do carro e versão do CSS) e site-html/css/home-publica.css (duas regras específicas da Home). Atualizado site-html/test-home-publica-browser.cjs e esta pasta de evidências. Sem alteração de backend, banco ou Supabase, sem deploy no Render. Workspace original, alterações pendentes e main local preservados.
