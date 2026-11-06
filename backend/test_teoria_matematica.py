"""Fórmulas: SQLite descartável, sem importar app.database configurado."""
import html
import json
import sys
import pytest
from fastapi import HTTPException
from app.teoria_html import preparar_conteudo
from test_teoria_html import ambiente, infraestrutura


def test_persistencia_fonte_edicao_e_legados(ambiente):
    _, cliente, factory, _ = ambiente
    from app.models import Material
    antigo = '<h2>Anterior</h2><p><strong>HTML antigo</strong> e literal \\(x\\).</p>'
    with factory() as db:
        db.add(Material(id=2, aula_id=1, tipo='TEXTO', titulo='HTML anterior',
                        conteudo=antigo, conteudo_formato='html_v1', ordem=2))
        db.commit()
    anteriores = cliente.get('/aulas/1/materiais').json()
    fonte = r"\forall x,\; P(x) \Rightarrow Q(x)" + "\n  " + r"\text{a  b}"
    conteudo = '<p>Exemplo <span class="ro-math-inline">' + html.escape(fonte) + '</span></p>'
    payload = dict(aula_id=1, tipo='TEXTO', titulo='Matemática', conteudo_formato='html_v1', conteudo=conteudo)
    resposta = cliente.post('/materiais', json=payload)
    assert resposta.status_code == 200, resposta.text
    id = resposta.json()['id']
    assert resposta.json()['conteudo'] == conteudo
    assert cliente.get('/aulas/1/materiais').json()[:2] == anteriores
    payload['conteudo'] = '<figure class="ro-math-display">' + html.escape(fonte + r" \land R") + '</figure>'
    resposta = cliente.put(f'/materiais/{id}', json=payload)
    assert resposta.status_code == 200, resposta.text
    reaberto = next(x for x in cliente.get('/aulas/1/materiais').json() if x['id'] == id)
    assert reaberto['conteudo'] == payload['conteudo']
    assert reaberto['conteudo_formato'] == 'html_v1'


@pytest.mark.parametrize('conteudo', [
    '<span class="ro-math-inline"></span>',
    '<span class="ro-math-inline">' + 'a' * 4097 + '</span>',
    '<span class="ro-math-inline">x<b>y</b></span>',
    '<span class="ro-math-inline">x<!--comentário-->y</span>',
    '<figure class="ro-math-display"><img src="https://example.com/x"></figure>',
    '<span class="ro-math-inline">x',
    '<span class="ro-math-inline">x</span>' * 201,
    '<span class="ro-math-inline">x&#0;y</span>',
])
def test_fontes_invalidas_sao_recusadas(conteudo):
    with pytest.raises(HTTPException) as erro:
        preparar_conteudo(conteudo, 'html_v1')
    assert erro.value.status_code == 422


def test_sanitizacao_restrita_e_idempotente():
    entrada = '<p onclick="evil()">Seguro</p><span class="ro-math-inline" id="x" style="color:red" onmouseover="evil()">x &lt; y</span><svg onload="evil()"></svg><script>evil()</script>'
    limpo = preparar_conteudo(entrada, 'html_v1')
    assert limpo == '<p>Seguro</p><span class="ro-math-inline">x &lt; y</span>'
    assert preparar_conteudo(limpo, 'html_v1') == limpo
    legado = r'Literal \(x\) <b>texto</b>'
    assert preparar_conteudo(legado, 'texto_puro') == legado
    assert preparar_conteudo('<p>' + legado + '</p>', 'html_v1') == '<p>' + legado + '</p>'


def ponte_browser():
    # Rotas reais + commit/refresh reais em SQLite em memória. Nenhuma configuração
    # DATABASE_URL é lida. Protocolo stdin/stdout restrito ao processo do teste.
    infra = infraestrutura.__wrapped__()
    fixture = None
    try:
        recurso = next(infra)
        fixture = ambiente.__wrapped__(recurso)
        _, cliente, _, _ = next(fixture)
        print(json.dumps({'ready': True}), flush=True)
        for linha in sys.stdin:
            req = json.loads(linha)
            try:
                r = cliente.request(req['method'], req['path'], json=req.get('json'))
                print(json.dumps({'status': r.status_code, 'body': r.json()}), flush=True)
            except Exception as erro:
                print(json.dumps({'error': str(erro)}), flush=True)
    finally:
        if fixture:
            fixture.close()
        infra.close()


if __name__ == '__main__' and '--bridge' in sys.argv:
    ponte_browser()
