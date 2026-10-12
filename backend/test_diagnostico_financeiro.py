import json
from types import SimpleNamespace
from unittest.mock import Mock, patch
import pytest
import requests
from fastapi import HTTPException
from app import transacoes_mp as tx
from app import diagnostico_financeiro as diag
from test_compras_fluxo import ambiente_compra, motor
from test_pausa_financeira import modo

SEGREDO='Authorization segredo-token email@privado.local https://privado.local/999999'

def conferir(caplog, etapa, categoria):
    records=[r for r in caplog.records if r.name=='resumao.financeiro']
    assert records
    for r in records:
        assert r.exc_info is None
        for segredo in (SEGREDO, 'segredo-token', 'Authorization', 'email@privado.local', 'https://privado.local', '999999'):
            assert segredo not in r.getMessage()
        d=json.loads(r.getMessage().removeprefix('financeiro '))
        assert set(d) <= {'etapa','categoria','duracao_ms','notificacao_id','status_http'}
    assert any(json.loads(r.getMessage().removeprefix('financeiro '))['etapa']==etapa and
               json.loads(r.getMessage().removeprefix('financeiro '))['categoria']==categoria for r in records)

@pytest.mark.parametrize('exc,categoria',[(requests.Timeout,'timeout'),(requests.ConnectionError,'conexao'),(requests.exceptions.SSLError,'tls'),(requests.RequestException,'transporte')])
def test_transporte_sanitizado(caplog,exc,categoria):
    with diag.contexto(1),patch.object(tx.requests,'get',side_effect=exc(SEGREDO)):
        with pytest.raises(HTTPException) as e:tx.consultar_pagamento('999999',{'Authorization':SEGREDO})
    assert e.value.status_code==502
    conferir(caplog,'consulta_pagamento',categoria)
    assert all('notificacao_id' in json.loads(r.getMessage().removeprefix('financeiro ')) for r in caplog.records if r.name=='resumao.financeiro')

@pytest.mark.parametrize('status,categoria',[(None,'ausente'),('','ausente'),({'privado':SEGREDO},'tipo_invalido'),(SEGREDO,'nao_reconhecido')])
def test_status_sanitizado(caplog,status,categoria):
    with pytest.raises(HTTPException) as e:tx.atualizar_estado_mp(SimpleNamespace(mp_status=None),{'status':status})
    assert e.value.status_code==502
    conferir(caplog,'interpretacao_status',categoria)

def test_merchant_http_json_transporte(caplog):
    dados={'order':{'id':'999999'}}
    for resposta in [Mock(status_code=403),Mock(status_code=200)]:
        resposta.json.side_effect=ValueError(SEGREDO)
        with patch.object(tx.requests,'get',return_value=resposta):
            with pytest.raises((HTTPException,ValueError)):tx.verificar_ordem_mp(dados,'999999',{'Authorization':SEGREDO})
    with patch.object(tx.requests,'get',side_effect=requests.Timeout(SEGREDO)):
        with pytest.raises(HTTPException) as e:tx.verificar_ordem_mp(dados,'999999',{})
    assert e.value.status_code==502
    for categoria in ('http','json_invalido','timeout'):conferir(caplog,'consulta_merchant_order',categoria)

@pytest.mark.parametrize('http,json_erro,categoria,codigo',[(403,False,'http',502),(200,True,'json_invalido',500)])
def test_inbox_correlacao_rollback(ambiente_compra,caplog,http,json_erro,categoria,codigo):
    main,client,factory=ambiente_compra[:3]
    assert modo(ambiente_compra,'RECUPERACAO').status_code==200
    p=main.app.state.protecao_financeira
    ident=p.armazenar('999999','diagnostico:teste','WEBHOOK')
    resposta=Mock(status_code=http)
    if json_erro:resposta.json.side_effect=ValueError(SEGREDO)
    with patch.object(main,'consultar_pagamento',return_value=resposta):
        r=client.post('/admin/financeiro/notificacoes/recuperar',json={'limite':1})
    assert r.status_code==200 and r.json()['resultados']==[{'id':ident,'processado':False,'erro_codigo':codigo}]
    conferir(caplog,'consulta_pagamento',categoria)
    from app.models import Pagamento,ContratacaoCurso
    from app.pausa_financeira import inbox
    with factory() as db:
        assert db.query(Pagamento).count()==0 and db.query(ContratacaoCurso).count()==0
        row=db.execute(inbox.select()).mappings().one()
        assert row['estado']=='ERRO' and row['tentativas']==1
    assert diag.notificacao.get() is None and diag.ultima.get() is None

def test_logging_nao_altera_excecao():
    with patch.object(diag.logger,'warning',side_effect=RuntimeError(SEGREDO)):
        with patch.object(tx.requests,'get',side_effect=requests.Timeout(SEGREDO)):
            with pytest.raises(HTTPException) as e:tx.consultar_pagamento('999999',{})
    assert e.value.status_code==502
