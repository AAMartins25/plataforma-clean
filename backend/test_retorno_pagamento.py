"""Confirmação de retorno com SQLite isolado e Mercado Pago sempre simulado."""
from datetime import datetime
import pytest
from app import models as m
from test_compras_fluxo import ambiente_compra,motor,demo

def iniciar(ambiente_compra):
    _,c,f,_,get=ambiente_compra
    with f() as db:did=demo(db)
    r=c.post('/checkout/mercadopago',json={'tempo_acesso_id':1,'demonstracao_id':did})
    assert r.status_code==200,r.text
    pid=r.json()['pagamento_id']
    return pid,did

def resposta_mp(get,pid,status='pending',method='pix',user=1):
    get.return_value.status_code=200
    get.return_value.json.return_value={
        'id':'123','status':status,'payment_method_id':method,'payment_type_id':'bank_transfer',
        'date_approved':datetime.utcnow().isoformat()+'Z',
        'transaction_amount':49.90,'currency_id':'BRL',
        'external_reference':f'user:{user}|curso:1|tempo:1|pagamento:{pid}'}

@pytest.mark.parametrize('status',['pending','in_process','rejected','cancelled','approved'])
def test_estado_confiavel_e_pix(ambiente_compra,status):
    _,c,f,post,get=ambiente_compra
    pid,did=iniciar(ambiente_compra);resposta_mp(get,pid,status)
    r=c.post('/pagamentos/confirmar',json={'payment_id':123,'curso_id':1,'status':'approved','payment_method_id':'forjado'})
    assert r.status_code==200,r.text
    assert r.json()['status']==status.upper()
    assert r.json()['payment_method_id']=='pix'
    assert r.json()['liberou_acesso']==(status=='approved')
    post.assert_called_once()
    with f() as db:
        assert db.query(m.ContratacaoCurso).count()==(1 if status=='approved' else 0)
        assert db.get(m.DemonstracaoCurso,did).ativo
        assert db.get(m.Pagamento,pid).status==status.upper()

def test_pendente_aprovado_posteriormente_e_repeticao(ambiente_compra):
    _,c,f,post,get=ambiente_compra
    pid,_=iniciar(ambiente_compra);resposta_mp(get,pid)
    assert c.post('/pagamentos/confirmar',json={'payment_id':123,'curso_id':1}).json()['status']=='PENDING'
    resposta_mp(get,pid,'approved')
    assert c.post('/pagamentos/confirmar',json={'payment_id':123,'curso_id':1}).json()['liberou_acesso'] is True
    repetida=c.post('/pagamentos/confirmar',json={'payment_id':123,'curso_id':1}).json()
    assert repetida['status']=='APPROVED' and repetida['liberou_acesso'] is False and repetida['payment_method_id']=='pix'
    with f() as db:
        assert db.query(m.ContratacaoCurso).count()==1
        assert db.query(m.PeriodoAcessoPagamento).count()==1
    post.assert_called_once()

def test_outro_aluno_nao_consulta_nem_libera(ambiente_compra):
    _,c,f,_,get=ambiente_compra
    pid,_=iniciar(ambiente_compra);resposta_mp(get,pid,'approved',user=2)
    assert c.post('/pagamentos/confirmar',json={'payment_id':123,'curso_id':1}).status_code==403
    with f() as db:assert db.query(m.ContratacaoCurso).count()==0

def test_ocorrencia_financeira_preserva_impedimento(ambiente_compra):
    _,c,f,_,get=ambiente_compra
    pid,_=iniciar(ambiente_compra)
    with f() as db:db.get(m.Pagamento,pid).ocorrencia_financeira='COBRANCA_DUPLICADA';db.commit()
    resposta_mp(get,pid,'approved')
    r=c.post('/pagamentos/confirmar',json={'payment_id':123,'curso_id':1})
    assert r.status_code==200,r.text
    assert r.json()['ocorrencia_financeira']=='COBRANCA_DUPLICADA'
    assert r.json()['liberou_acesso'] is False
    with f() as db:assert db.query(m.ContratacaoCurso).count()==0

def test_falha_mp_nao_aprova(ambiente_compra):
    _,c,f,_,get=ambiente_compra
    pid,_=iniciar(ambiente_compra);get.return_value.status_code=503;get.return_value.text='Simulado'
    assert c.post('/pagamentos/confirmar',json={'payment_id':123,'curso_id':1}).status_code==502
    with f() as db:
        assert db.get(m.Pagamento,pid).status=='PENDENTE'
        assert db.query(m.ContratacaoCurso).count()==0
