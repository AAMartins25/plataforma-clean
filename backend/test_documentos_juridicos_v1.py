"""Documentos recebidos: arquivos reais; apenas SQLite efêmero e MP simulado.
Não executa migrações nem os INSERTs preparados para revisão.
"""
from datetime import datetime, timezone
from hashlib import sha256
from html import unescape
import json
import os
from pathlib import Path
import re
import pytest
from app import models as m
from app import juridico as j
from preparar_documentos_juridicos import gerar
from test_compras_fluxo import ambiente_compra, motor, contrato
from test_aceites_juridicos import TABELAS

PACOTE = Path(__file__).parent / 'documentos_juridicos/1.0'
MANIFESTO = json.loads((PACOTE / 'manifesto.json').read_text())['documentos']

@pytest.fixture
def documentos_reais(ambiente_compra, monkeypatch):
    with ambiente_compra[2]() as db:
        m.Base.metadata.create_all(db.get_bind(), tables=TABELAS)
        for item in MANIFESTO:
            db.add(m.DocumentoJuridicoVersao(id=101 if item['tipo']=='TERMOS' else 102,
                tipo=item['tipo'], versao=item['versao'], titulo=item['titulo'],
                conteudo=(PACOTE/item['texto']).read_bytes().decode('utf-8'),
                sha256=item['texto_sha256'], pdf_sha256=item['pdf_sha256'], publicado_em=datetime.now(timezone.utc)))
        db.flush()
        db.add(m.PoliticaAceiteJuridico(id=1, habilitada=False, termos_id=101, privacidade_id=102))
        db.commit()
    return ambiente_compra


def ativar_somente_na_fixture(ambiente):
    with ambiente[2]() as db:
        db.get(m.PoliticaAceiteJuridico, 1).habilitada=True; db.commit()


def pedido(**extra):
    return {'tempo_acesso_id':1, 'aceite_juridico':{'aceito':True,'termos_id':101,'privacidade_id':102},**extra}

@pytest.mark.parametrize('item', MANIFESTO, ids=lambda x:x['tipo'])
def test_integridade_pacote(item):
    pdf=(PACOTE/item['pdf']).read_bytes();texto=(PACOTE/item['texto']).read_bytes()
    assert sha256(pdf).hexdigest()==item['pdf_sha256']
    assert sha256(texto).hexdigest()==item['texto_sha256']
    assert pdf.startswith(b'%PDF-') and pdf.rstrip().endswith(b'%%EOF')
    assert texto.decode().count('[A PREENCHER]')==item['campos_a_preencher']
    assert item['campos_a_preencher']==(6 if item['tipo']=='TERMOS' else 7)
    assert all(p['extratores_concordam_sem_espacos'] for p in item['paginas'])
    assert [int(x) for x in re.findall(r'^\s*(\d+)\. [A-ZÁÉÍÓÚÂÊÔÃÕÇ]',texto.decode(),re.M)]==list(range(1,23))


def test_sql_preparado_sem_ativacao():
    bytipo={d['tipo']:d for d in MANIFESTO}
    t,p=bytipo['TERMOS'],bytipo['PRIVACIDADE']
    esperado=gerar((PACOTE/t['texto']).read_bytes(),(PACOTE/p['texto']).read_bytes(),
        termos_pdf_sha256=t['pdf_sha256'],privacidade_pdf_sha256=p['pdf_sha256'])
    assert (PACOTE/'documentos-1.0.sql').read_bytes().decode()==esperado
    assert esperado.count('INSERT INTO documentos_juridicos_versoes')==2
    assert 'politica_aceite_juridico' not in esperado
    assert esperado.count('[A PREENCHER]')==13
    assert 'UPDATE' not in esperado and 'DELETE' not in esperado


@pytest.mark.parametrize('item', MANIFESTO, ids=lambda x:x['tipo'])
def test_recupera_texto_integral_e_pdf_original(documentos_reais,item):
    _,c,_,post,get=documentos_reais
    id=101 if item['tipo']=='TERMOS' else 102
    r=c.get(f'/public/juridico/documentos/{id}')
    assert r.status_code==200,r.text
    if os.getenv('EVIDENCIAS_JURIDICO_DIR'):
        destino=Path(os.environ['EVIDENCIAS_JURIDICO_DIR']);destino.mkdir(parents=True,exist_ok=True)
        (destino/f'{id}.html').write_bytes(r.content)
    extraido=unescape(re.search(r'<pre[^>]*>(.*?)</pre>',r.text,re.S).group(1))
    assert extraido==(PACOTE/item['texto']).read_bytes().decode()
    original=c.get('/public/juridico/arquivos/'+item['pdf_sha256']+'.pdf')
    assert original.status_code==200 and original.headers['content-type']=='application/pdf'
    assert original.content==(PACOTE/item['pdf']).read_bytes()
    assert sha256(original.content).hexdigest()==item['pdf_sha256']
    post.assert_not_called();get.assert_not_called()


def test_ativacao_permanece_desabilitada(documentos_reais):
    _,c,f,_,_=documentos_reais
    assert c.get('/public/juridico/vigente').json()=={'obrigatorio':False,'documentos':[]}
    with f() as db:
        assert db.get(m.PoliticaAceiteJuridico,1).habilitada is False
        assert db.query(m.AceiteJuridico).count()==0


def test_vinculos_e_renovacao_preservam_versoes(documentos_reais):
    _,c,f,post,get=documentos_reais
    ativar_somente_na_fixture(documentos_reais)
    for _ in range(2):
        r=c.post('/checkout/mercadopago',json=pedido())
        assert r.status_code==200,r.text
    with f() as db:
        pagamento=db.query(m.Pagamento).one()
        ids=[x.aceite_id for x in db.query(m.AceiteJuridicoPagamento).filter_by(pagamento_id=pagamento.id)]
        assert len(ids)==2
        for aid in ids:
            documentos=db.query(m.DocumentoJuridicoVersao).join(m.AceiteJuridicoDocumento,
                m.AceiteJuridicoDocumento.documento_id==m.DocumentoJuridicoVersao.id).filter(m.AceiteJuridicoDocumento.aceite_id==aid).all()
            assert {d.sha256 for d in documentos}=={x['texto_sha256'] for x in MANIFESTO}
            assert {d.pdf_sha256 for d in documentos}=={x['pdf_sha256'] for x in MANIFESTO}
        cid=contrato(db,dias=10)
    assert post.call_count==get.call_count==1
    r=c.post('/checkout/mercadopago',json=pedido(tipo_compra='RENOVACAO',contratacao_id=cid))
    assert r.status_code==200,r.text
    with f() as db:
        assert db.query(m.AceiteJuridico).count()==3
        assert db.query(m.AceiteJuridicoDocumento).count()==6
        assert db.query(m.AceiteJuridicoPagamento).count()==3
        assert db.query(m.PeriodoAcessoPagamento).count()==0


def test_rejeita_troca_de_pdf_documento(documentos_reais):
    _,c,f,post,get=documentos_reais
    ativar_somente_na_fixture(documentos_reais)
    with f() as db:
        db.get(m.DocumentoJuridicoVersao,101).pdf_sha256=db.get(m.DocumentoJuridicoVersao,102).pdf_sha256;db.commit()
    assert c.post('/checkout/mercadopago',json=pedido()).status_code==503
    post.assert_not_called();get.assert_not_called()


def test_pdf_corrompido_nao_abre_checkout(documentos_reais,monkeypatch,tmp_path):
    _,c,_,post,get=documentos_reais
    ativar_somente_na_fixture(documentos_reais)
    pacote=tmp_path/'1.0';pacote.mkdir()
    (pacote/'manifesto.json').write_text(json.dumps({'documentos':MANIFESTO}))
    for item in MANIFESTO:(pacote/item['pdf']).write_bytes(b'%PDF-fixture corrompida')
    monkeypatch.setattr(j,'ARQUIVOS_JURIDICOS',tmp_path)
    assert c.post('/checkout/mercadopago',json=pedido()).status_code==503
    post.assert_not_called();get.assert_not_called()


def test_versao_inexistente_nao_abre_checkout(documentos_reais):
    _,c,_,post,get=documentos_reais
    ativar_somente_na_fixture(documentos_reais)
    p=pedido();p['aceite_juridico']['termos_id']=999
    assert c.post('/checkout/mercadopago',json=p).status_code==409
    post.assert_not_called();get.assert_not_called()


def test_pdfs_da_pasta_definitiva_e_links(documentos_reais):
    _,c,_,_,_=documentos_reais
    ativar_somente_na_fixture(documentos_reais)
    resposta=c.get('/public/juridico/vigente').json()
    site=Path(__file__).parent.parent/'site-html'
    for d in resposta['documentos']:
        esperado=next(x for x in MANIFESTO if x['tipo']==d['tipo'])
        assert d['pdf_site_url']=='juridico/'+esperado['pdf']
        assert sha256((site/d['pdf_site_url']).read_bytes()).hexdigest()==d['pdf_sha256']==esperado['pdf_sha256']


def test_ativacao_e_desativacao_sem_deploy(documentos_reais,monkeypatch):
    monkeypatch.delenv('ACEITE_JURIDICO_DISPONIVEL',raising=False)
    _,c,f,post,get=documentos_reais
    assert c.get('/public/juridico/vigente').json()['obrigatorio'] is False
    assert c.post('/checkout/mercadopago',json={'tempo_acesso_id':1}).status_code==200
    ativar_somente_na_fixture(documentos_reais)
    assert c.get('/public/juridico/vigente').json()['obrigatorio'] is True
    assert c.post('/checkout/mercadopago',json={'tempo_acesso_id':1}).status_code==400
    assert c.post('/checkout/mercadopago',json=pedido()).status_code==200
    with f() as db:
        db.get(m.PoliticaAceiteJuridico,1).habilitada=False;db.commit()
    assert c.get('/public/juridico/vigente').json()['obrigatorio'] is False
    assert c.post('/checkout/mercadopago',json={'tempo_acesso_id':1}).status_code==200
    assert post.call_count==1 and get.call_count==2


def test_backend_antes_da_migracao_compativel(ambiente_compra):
    from sqlalchemy import inspect
    _,c,f,post,_=ambiente_compra
    with f() as db: assert not inspect(db.connection()).has_table('politica_aceite_juridico')
    assert c.get('/public/juridico/vigente').json()=={'obrigatorio':False,'documentos':[]}
    assert c.post('/checkout/mercadopago',json={'tempo_acesso_id':1}).status_code==200
    assert post.call_count==1
    with f() as db: assert not inspect(db.connection()).has_table('politica_aceite_juridico')


def test_startup_nao_antecipa_migracao_021():
    import ast
    from types import SimpleNamespace
    from unittest.mock import Mock
    arvore=ast.parse((Path(__file__).parent/'app/database.py').read_text())
    startup=arvore.body[-1]
    metadata=SimpleNamespace(sorted_tables=list(m.Base.metadata.sorted_tables),create_all=Mock())
    env={'os':SimpleNamespace(getenv=lambda _:None),'Base':SimpleNamespace(metadata=metadata),
         'engine':object(),'TABELAS_JURIDICAS':m.TABELAS_JURIDICAS}
    exec(compile(ast.Module(body=[startup],type_ignores=[]),'startup-controlado','exec'),env)
    tabelas=metadata.create_all.call_args.kwargs['tables']
    assert not {t.name for t in tabelas}&m.TABELAS_JURIDICAS
    assert {'pagamentos','contratacoes_curso'}<={t.name for t in tabelas}


def test_sql_021_aditivo_sem_backfill():
    sql=(Path(__file__).parent/'migrations/021_aceites_juridicos.sql').read_text()
    # Fora do corpo da função que rejeita mutações, a migração só cria novas estruturas.
    assert not re.search(r'\b(UPDATE|DELETE FROM|INSERT INTO)\s+(pagamentos|contratacoes_curso|acessos_curso)\b',sql,re.I)
    assert "VALUES (1, FALSE)" in sql
    assert sql.count('CREATE TRIGGER imutavel BEFORE UPDATE OR DELETE')==4
    assert 'ON DELETE CASCADE' not in sql


@pytest.mark.parametrize('canal',['confirmacao','webhook'])
def test_pagamento_anterior_preservado_apos_ativar(documentos_reais,canal):
    from apoio_testes_juridicos import preparar,confirmar
    from apoio_testes_juridicos import notificar
    from unittest.mock import patch
    main,c,f,_,_=documentos_reais
    pid,dados,tx,_=preparar(documentos_reais)
    ativar_somente_na_fixture(documentos_reais)
    tx['101']=dados(101,'approved')
    if canal=='confirmacao':
        assert confirmar(documentos_reais,101).json()['liberou_acesso']
    else:
        with patch.object(main,'validar_assinatura_mercadopago',return_value=True):
            r=notificar(documentos_reais)
            assert r.status_code==200,r.text
    with f() as db:
        assert db.get(m.Pagamento,pid).aprovado_em is not None
        assert db.query(m.PeriodoAcessoPagamento).count()==1
        assert db.query(m.AceiteJuridico).count()==0
