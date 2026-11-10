"""Gráficos reais rasterizados, SQLite e Storage em memória; sem serviços externos."""
from io import BytesIO
from pathlib import Path
import sys

from PIL import Image, ImageDraw, ImageFont
import pytest
from app import models as m
from test_imagens_teoria import ambiente_imagens, aulas, infraestrutura
from test_questoes_html import rica


def grafico(formato):
    imagem = Image.new('RGB', (1000, 600), 'white')
    draw = ImageDraw.Draw(imagem)
    fonte = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 42)
    draw.text((170, 15), 'Vendas por trimestre', fill='black', font=fonte)
    draw.line([(125, 100), (125, 490), (940, 490)], fill='black', width=5)
    for x, altura, rotulo in [(220, 150, 'T1'), (440, 240, 'T2'), (660, 330, 'T3')]:
        draw.rectangle((x, 490-altura, x+130, 487), fill='#135ba3')
        draw.text((x+30, 510), rotulo, fill='black', font=fonte)
        draw.text((x+25, 440-altura), str(altura//3), fill='black', font=fonte)
    out = BytesIO(); imagem.save(out, format=formato, **({'quality':95} if formato != 'PNG' else {}))
    return out.getvalue()


@pytest.mark.parametrize('formato,ext,mime', [('PNG','png','image/png'),('JPEG','jpg','image/jpeg'),('WEBP','webp','image/webp')])
def test_grafico_todos_campos_persistencia_e_acesso(ambiente_imagens, formato, ext, mime):
    _, c, factory, perfil, storage = ambiente_imagens
    r = c.post('/admin/imagens/arquivos', files={'arquivos':('grafico.'+ext,grafico(formato),mime)})
    assert r.status_code == 200, r.text
    img = r.json()['imagens'][0]
    assert (img['largura'],img['altura']) == (1000,600)
    html = f'<figure class="image"><img src="{img["src"]}" alt="Gráfico de vendas" width="1000" height="600"><figcaption>Vendas por trimestre</figcaption></figure>'
    p = rica('MULTIPLA_5'); p['enunciado']=html; p['comentario']=html
    for alt in p['alternativas']: alt['texto']=html
    r = c.post('/questoes',json=p); assert r.status_code==200,r.text
    id = r.json()['id']
    def reabrir(): return next(q for q in c.get('/baterias/1/questoes').json() if q['id']==id)
    q = reabrir(); ids = [a['id'] for a in q['alternativas']]
    assert q['enunciado']==html and q['comentario']==html
    assert all(a['texto']==html and a['texto_formato']=='html_v1' for a in q['alternativas'])
    p['enunciado']='<p>Enunciado editado</p>'+html
    assert c.put(f'/questoes/{id}',json=p).status_code==200
    assert reabrir()['enunciado']==p['enunciado']
    assert [a['id'] for a in reabrir()['alternativas']]==ids
    # O raster normalizado mantém as dimensões, os eixos e o contraste do gráfico.
    with factory() as db:
        imagem=db.get(m.ImagemTeoria,img['id']);dados,tipo=storage.objetos[imagem.chave]
        assert tipo==mime
        with Image.open(BytesIO(dados)) as aberta:
            assert aberta.size==(1000,600)
            r,g,b=aberta.convert('RGB').getpixel((250,450))
            assert b > r+60 and b > g
    for i in range(9): assert c.post('/questoes',json=rica('CERTO_ERRADO')).status_code==200
    assert c.put('/baterias/1/concluir',json={}).status_code==200
    perfil(False)
    assert c.post('/baterias/1/imagens/assinaturas?contratacao_id=1',json={'ids':[img['id']]}).status_code==200
    assert c.post('/baterias/1/imagens/assinaturas?contratacao_id=2',json={'ids':[img['id']]}).status_code==403


if __name__=='__main__':
    pasta=Path(sys.argv[1]);pasta.mkdir(parents=True,exist_ok=True)
    for formato,ext in [('PNG','png'),('JPEG','jpg'),('WEBP','webp')]:
        (pasta/('grafico.'+ext)).write_bytes(grafico(formato))
