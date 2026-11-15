from app.descricao_publica import MARCADOR, preparar_descricao, descricao_para_visitante


def test_tabela_preserva_estrutura_formatacao_e_celulas_mescladas():
    html = '<p>Texto anterior</p><figure class="table"><table><thead><tr><th>Plano</th><th>Valor</th></tr></thead><tbody><tr><td rowspan="2"><strong>Resumo</strong></td><td><i>49,90</i></td></tr><tr><td colspan="2">Final</td></tr></tbody></table></figure>'
    salvo = preparar_descricao({'descricao_publica': html, 'descricao_publica_formato': 'html_v1'}, None)
    assert salvo == MARCADOR + html.replace('<figure class="table">', '').replace('</figure>', '')
    assert preparar_descricao({'descricao_publica': salvo}, salvo) == salvo
    publico = descricao_para_visitante(salvo)
    assert publico['descricao_publica_html'] == salvo[len(MARCADOR):]
    assert 'Plano\tValor\n' in publico['descricao_publica']
    assert 'Resumo\t49,90\nFinal' in publico['descricao_publica']
    assert preparar_descricao({}, salvo) == salvo


def test_tabela_nao_autoriza_estilos_eventos_ou_conteudo_ativo():
    html = '<table style="width:99999px" onclick="evil()"><tr><td colspan="2" rowspan="3" onmouseover="evil()" style="color:red" data-x="1"><script>evil()</script><img src=x onerror=evil()><a href="javascript:evil()">Texto</a></td></tr></table>'
    publico = descricao_para_visitante(preparar_descricao({'descricao_publica': html, 'descricao_publica_formato': 'html_v1'}, None))
    assert '<td colspan="2" rowspan="3">Texto</td>' in publico['descricao_publica_html'] or '<td rowspan="3" colspan="2">Texto</td>' in publico['descricao_publica_html']
    for proibido in ['style=', 'onclick', 'onmouseover', 'onerror', '<script', '<img', 'javascript:', 'data-x=']:
        assert proibido not in publico['descricao_publica_html']
