"""E-mails apenas simulados: nenhuma credencial real, dotenv ou acesso externo."""
import base64
import zlib
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
import requests
from sqlalchemy import select, update
from app import models as m
from app.emails_pagamentos import (EmailsPagamentos, Config, fila, metadata,
                                  boleto_linha, hash_payload, instrucoes, Invalido)
from test_compras_fluxo import ambiente_compra, motor
from test_transacoes_mp import preparar, confirmar
from test_pausa_financeira import enviar, modo, admin


def pix(cents=4990, tentativa=None):
    # Payload EMV sintético com CRC correto; QR PNG de teste 1x1.
    codigo='0002015303986'
    valor=f'{cents/100:.2f}'
    codigo+='54'+f'{len(valor):02}'+valor
    if tentativa:
        sub='05'+f'{len(str(tentativa)):02}'+str(tentativa)
        codigo+='62'+f'{len(sub):02}'+sub
    codigo+='6304'
    crc=0xffff
    for b in codigo.encode():
        crc^=b<<8
        for _ in range(8):crc=((crc<<1)^0x1021)&0xffff if crc&0x8000 else (crc<<1)&0xffff
    codigo+=f'{crc:04X}'
    def chunk(tag,d):
        b=tag+d
        return len(d).to_bytes(4,'big')+b+zlib.crc32(b).to_bytes(4,'big')
    png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',b'\x00\x00\x00\x01'*2+b'\x08\x02\x00\x00\x00')+chunk(b'IDAT',zlib.compress(b'\x00\x00\x00\x00'))+chunk(b'IEND',b'')
    imagem=base64.b64encode(png).decode()
    return {'qr_code':codigo,'qr_code_base64':imagem}


def barcode(cents=4990):
    b='3419'+'0'+'1000'+f'{cents:010}'+'1234567890123456789012345'
    sem=b[:4]+b[5:]
    soma=sum(int(v)*(2+i%8) for i,v in enumerate(reversed(sem)))
    dv=11-soma%11
    return b[:4]+str(1 if dv in (0,10,11) else dv)+b[5:]


@pytest.fixture
def emails(ambiente_compra, request):
    a=ambiente_compra
    if a[2].kw['bind'].dialect.name=='postgresql':
        from pathlib import Path
        with a[2].kw['bind'].connect() as c:
            c.connection.driver_connection.execute((Path(__file__).parent/'migrations/019_emails_pagamentos.sql').read_text())
    else:metadata.create_all(a[2].kw['bind'])
    config=Config(True,datetime.now(timezone.utc)-timedelta(hours=1),
                  'Resumão Online <email@teste.local>','resend-chave-simulada',30,3)
    s=EmailsPagamentos(a[2].kw['bind'],a[2],a[0].mp_headers,config)
    a[0].app.state.emails_pagamentos=s
    cupom = getattr(request, 'param', False)
    if cupom:
        with a[2]() as db:
            db.get(m.TempoAcessoCurso,1).valor_cents=400
            db.commit()
    pid,dados,tx,_=preparar(a,cupom=cupom)
    def completo(ident=101,status='pending',metodo='pix'):
        d=dados(ident,status)
        d.update(payment_method_id=metodo,payment_type_id='bank_transfer' if metodo=='pix' else 'ticket',
                 date_of_expiration=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat())
        cents=round(d['transaction_amount']*100)
        if metodo=='pix':d['point_of_interaction']={'transaction_data':pix(cents)}
        else:d.update(barcode={'content':barcode(cents)},transaction_details={'external_resource_url':'https://www.mercadopago.com/mlb/payments/ticket/helper?hash=teste'})
        return d
    tx['101']=completo()
    post=a[3];post.reset_mock();post.return_value=Mock(status_code=200)
    post.return_value.json.return_value={'id':'recibo-simulado'}
    return a,s,pid,tx,completo,post


def job(s,pid,tipo='PENDENTE'):
    with s.engine.connect() as c:return dict(c.execute(select(fila).where(fila.c.pagamento_id==pid,fila.c.tipo==tipo)).mappings().one())


def test_pix_completo_aceito_persistente_mensagem_e_repeticao(emails):
    a,s,pid,tx,_,post=emails
    assert confirmar(a,101).json()['email_instrucoes_aceito'] is False
    s.rodada()
    assert job(s,pid)['estado']=='ACEITO' and job(s,pid)['tentativas']==1
    corpo=post.call_args.kwargs['json']
    assert corpo['to']==['1@teste.local'] and corpo['attachments'][0]['content_id']=='pix-qrcode'
    assert tx['101']['point_of_interaction']['transaction_data']['qr_code'] in corpo['text']
    assert 'R$ 49,90' in corpo['text']
    assert confirmar(a,101).json()['email_instrucoes_aceito'] is True
    s.rodada();s.rodada();assert post.call_count==1
    with a[2]() as db:assert db.query(m.ContratacaoCurso).count()==0


def test_boleto_completo_sem_login(emails):
    a,s,pid,tx,completo,post=emails;tx['101']=completo(metodo='bolbradesco')
    assert confirmar(a,101).status_code==200
    s.rodada();assert job(s,pid)['estado']=='ACEITO'
    corpo=post.call_args.kwargs['json']
    assert boleto_linha(barcode(),4990) in corpo['text']
    assert tx['101']['transaction_details']['external_resource_url'] in corpo['text']
    assert 'access_token' not in corpo['text'] and 'login' not in corpo['text']
    assert confirmar(a,101).json()['email_instrucoes_aceito'] is True


@pytest.mark.parametrize('campo',['qr','imagem','vencimento','crc','png','expirado'])
def test_pix_incompleto_invalido_ou_vencido_nao_envia(emails,campo):
    a,s,pid,tx,_,post=emails
    td=tx['101']['point_of_interaction']['transaction_data']
    if campo=='qr':td.pop('qr_code')
    if campo=='imagem':td.pop('qr_code_base64')
    if campo=='vencimento':tx['101'].pop('date_of_expiration')
    if campo=='crc':td['qr_code']=td['qr_code'][:-4]+'0000'
    if campo=='png':td['qr_code_base64']=base64.b64encode(b'invalido').decode()
    if campo=='expirado':tx['101']['date_of_expiration']=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
    assert confirmar(a,101).status_code==200
    s.rodada();post.assert_not_called()
    assert job(s,pid)['estado'] in {'DADOS_PENDENTES','SUSPENSO'}
    assert confirmar(a,101).json()['email_instrucoes_aceito'] is False


@pytest.mark.parametrize('campo',['linha','dv','link','host','http'])
def test_boleto_invalido_nao_envia(emails,campo):
    a,s,pid,tx,completo,post=emails;tx['101']=completo(metodo='bolbradesco')
    if campo=='linha':tx['101']['barcode']['content']=''
    if campo=='dv':tx['101']['barcode']['content']=barcode()[:4]+str((int(barcode()[4])+1)%10)+barcode()[5:]
    if campo=='link':tx['101']['transaction_details']['external_resource_url']=''
    if campo=='host':tx['101']['transaction_details']['external_resource_url']='https://conta-invalida.example/boleto'
    if campo=='http':tx['101']['transaction_details']['external_resource_url']='http://www.mercadopago.com/boleto'
    assert confirmar(a,101).status_code==200
    s.rodada();post.assert_not_called()


@pytest.mark.parametrize('status',['approved','cancelled','rejected','charged_back','refunded','in_mediation'])
def test_mudanca_no_provedor_nao_envia_instrucoes(emails,status):
    a,s,pid,tx,completo,post=emails
    assert confirmar(a,101).status_code==200
    s.descobrir();tx['101']=completo(status=status)
    s.processar_um();post.assert_not_called();assert job(s,pid)['estado']=='SUSPENSO'


def test_dados_disponiveis_depois_sem_mensagem_incompleta(emails):
    a,s,pid,tx,completo,post=emails
    tx['101']['point_of_interaction']['transaction_data'].pop('qr_code_base64')
    assert confirmar(a,101).status_code==200
    s.rodada();post.assert_not_called();assert not confirmar(a,101).json()['email_instrucoes_aceito']
    tx['101']=completo()
    with s.engine.begin() as c:c.execute(update(fila).values(proxima_consulta_em=s.clock()-timedelta(seconds=1)))
    s.rodada();assert job(s,pid)['estado']=='ACEITO'


def test_duas_tentativas_nao_misturam_cobrancas(emails):
    a,s,pid,tx,completo,post=emails
    for ident in (101,102):
        tx[str(ident)]=completo(ident)
        tx[str(ident)]['point_of_interaction']['transaction_data'].update(pix(tentativa=ident))
        assert confirmar(a,ident).status_code==200
    s.rodada()
    with s.engine.connect() as c:
        rows=c.execute(select(fila).where(fila.c.tipo=='PENDENTE')).mappings().all()
    assert len(rows)==2 and all(r['estado']=='ACEITO' for r in rows)
    keys=[c.kwargs['headers']['Idempotency-Key'] for c in post.call_args_list]
    assert len(set(keys))==2
    for chamada,ident in zip(post.call_args_list,(101,102)):
        assert pix(tentativa=ident)['qr_code'] in chamada.kwargs['json']['text']
        assert pix(tentativa=203-ident)['qr_code'] not in chamada.kwargs['json']['text']
    with a[2]() as db:assert db.query(m.ContratacaoCurso).count()==0


@pytest.mark.parametrize('metodo,tipo,forma',[('pix','bank_transfer','Pix'),('visa','credit_card','Cartão de crédito'),('bolbradesco','ticket','Boleto')])
def test_aprovado_depois_do_acesso_sem_browser_duplicata_excluida(emails,metodo,tipo,forma):
    a,s,pid,tx,completo,post=emails
    for ident in (101,102):
        tx[str(ident)]={**completo(ident,'approved',metodo),'payment_type_id':tipo}
        assert enviar(a,ident,f'aprovacao-{ident}').status_code==200
    s.rodada()
    with a[2]() as db:
        assert db.query(m.ContratacaoCurso).count()==1
        assert db.query(m.PeriodoAcessoPagamento).count()==1
    assert post.call_count==1
    corpo=post.call_args.kwargs['json']
    assert corpo['subject']=='Compra aprovada no Resumão Online!'
    assert '4 meses' in corpo['text'] and 'R$ 49,90' in corpo['text'] and forma in corpo['text']
    assert "'Meus Cursos'" in corpo['text']
    assert job(s,pid,'APROVADO')['estado']=='ACEITO'
    enviar(a,101,'aprovacao-repetida');s.rodada();assert post.call_count==1


def test_falha_resend_nao_reverte_pagamento_e_reenvio_controlado(emails):
    a,s,pid,tx,completo,post=emails;tx['101']=completo(status='approved')
    assert enviar(a,101,'aprovado').status_code==200
    post.return_value.status_code=503
    s.rodada();assert job(s,pid,'APROVADO')['estado']=='ERRO'
    with a[2]() as db:assert db.query(m.ContratacaoCurso).count()==1
    s.rodada();assert post.call_count==1
    post.return_value.status_code=200;s.reenviar(pid,'APROVADO');s.rodada()
    assert job(s,pid,'APROVADO')['estado']=='ACEITO' and post.call_count==2
    assert post.call_args_list[0].kwargs['headers']['Idempotency-Key']==post.call_args_list[1].kwargs['headers']['Idempotency-Key']
    assert post.call_args_list[0].kwargs['json']==post.call_args_list[1].kwargs['json']


def test_aceitacao_com_resposta_perdida_deduplicada_e_limite_24h(emails,caplog):
    a,s,pid,tx,_,post=emails;assert confirmar(a,101).status_code==200
    post.side_effect=requests.Timeout('TOKEN-SECRETO/PAYLOAD-PESSOAL')
    s.rodada();assert job(s,pid)['estado']=='INCERTO' and not s.aceito(pid,tx['101'])
    assert 'TOKEN-SECRETO' not in caplog.text and 'PAYLOAD-PESSOAL' not in caplog.text
    post.side_effect=None;s.reenviar(pid,'PENDENTE');s.rodada()
    assert job(s,pid)['estado']=='ACEITO'
    with pytest.raises(Invalido):s.reenviar(pid,'PENDENTE')
    assert len({c.kwargs['headers']['Idempotency-Key'] for c in post.call_args_list})==1


def test_janela_expirada_nao_repete_e_historicos_excluidos(emails):
    a,s,pid,tx,_,post=emails;assert confirmar(a,101).status_code==200
    s.descobrir()
    with s.engine.begin() as c:c.execute(update(fila).values(estado='INCERTO',tentativas=1,
        primeiro_envio_em=s.clock()-timedelta(hours=24),payload={'teste':'congelado'},payload_hash='a'*64))
    with pytest.raises(Invalido):s.reenviar(pid,'PENDENTE')
    post.assert_not_called()
    s.config=replace(s.config,desde=s.clock()+timedelta(hours=1))
    with s.engine.begin() as c:c.execute(fila.delete())
    s.descobrir()
    with s.engine.connect() as c:assert c.execute(select(fila)).all()==[]


def test_pausa_e_config_desligada_sem_efeitos(emails):
    a,s,pid,tx,_,post=emails;assert confirmar(a,101).status_code==200
    modo(a,'PAUSADO');s.rodada();post.assert_not_called()
    with s.engine.connect() as c:assert c.execute(select(fila)).all()==[]
    s.config=Config();assert not s.aceito(pid,tx['101']);s.rodada();post.assert_not_called()


def test_rotas_admin_reenvio_e_privacidade(emails):
    a,s,pid,tx,_,post=emails;assert confirmar(a,101).status_code==200
    post.return_value.status_code=503;s.rodada()
    route=f'/admin/emails-pagamentos/{pid}/PENDENTE/reenviar'
    assert a[1].post(route,json={}).status_code==403
    a[0].app.dependency_overrides.pop(a[0].get_usuario_atual)
    assert a[1].post(route,json={}).status_code==401
    admin(a);assert a[1].post(route,json={}).status_code==200
    resposta=a[1].get('/admin/emails-pagamentos').json()
    assert 'resend-chave-simulada' not in str(resposta) and '1@teste.local' not in str(resposta)
    assert 'payload' not in str(resposta)

@pytest.mark.parametrize('alteracao',['valor','imagem_truncada','png_crc'])
def test_pix_conteudo_inconsistente_nao_envia(emails,alteracao):
    a,s,pid,tx,_,post=emails
    td=tx['101']['point_of_interaction']['transaction_data']
    if alteracao=='valor':td.update(pix(352))
    else:
        b=base64.b64decode(td['qr_code_base64'])
        b=b[:-12] if alteracao=='imagem_truncada' else b[:-1]+bytes([b[-1]^1])
        td['qr_code_base64']=base64.b64encode(b).decode()
    assert confirmar(a,101).status_code==200
    s.rodada();assert post.call_count==0
    assert job(s,pid)['estado']=='DADOS_PENDENTES'

@pytest.mark.parametrize('emails',[True],indirect=True)
def test_confirmacao_valor_real_com_desconto_e_snapshot(emails):
    a,s,pid,tx,completo,post=emails
    tx['101']=completo(status='approved')
    assert enviar(a,101,'aprovado-desconto').status_code==200
    s.rodada()
    assert job(s,pid,'APROVADO')['estado']=='ACEITO'
    body=post.call_args.kwargs['json']
    assert 'R$ 3,52' in body['text'] and '4 meses' in body['text']
    with a[2]() as db:
        p=db.get(m.Pagamento,pid)
        assert p.valor_cents==352 and p.codigo_cupom=='AW265'
        assert db.query(m.PeriodoAcessoPagamento).count()==1

@pytest.mark.parametrize('campo',['collector_id','external_reference','transaction_amount','currency_id','live_mode','id'])
def test_email_rejeita_vinculo_incompativel_sem_envio(emails,campo):
    a,s,pid,tx,_,post=emails
    assert confirmar(a,101).status_code==200
    s.descobrir()
    tx['101'][campo]={'collector_id':999,'external_reference':'checkout:incompativel','transaction_amount':1,'currency_id':'USD','live_mode':False,'id':999}[campo]
    s.processar_um();post.assert_not_called()
    assert not s.aceito(pid,tx['101'])

@pytest.mark.parametrize('mudanca',['sem_acesso','refunded','charged_back','in_mediation'])
def test_aprovado_sem_acesso_ou_com_ocorrencia_nao_envia(emails,mudanca):
    a,s,pid,tx,completo,post=emails
    tx['101']=completo(status='approved')
    assert enviar(a,101,'aprovacao').status_code==200
    s.descobrir()
    if mudanca=='sem_acesso':
        with a[2]() as db:
            db.query(m.AcessoCurso).update({'ativo':False});db.commit()
    else:tx['101']['status']=mudanca
    s.processar_um();post.assert_not_called()

@pytest.mark.parametrize('registro',['contestacao','reembolso'])
def test_ocorrencia_local_impede_email_sem_bloquear_acesso(emails,registro):
    a,s,pid,tx,completo,post=emails
    tx['101']=completo(status='approved')
    assert enviar(a,101,'aprovacao').status_code==200
    s.descobrir()
    with a[2]() as db:
        if registro=='contestacao':db.add(m.ContestacaoPagamento(pagamento_id=pid,status='ABERTA',valor_cents=4990))
        else:db.add(m.ReembolsoFinanceiro(pagamento_id=pid,metodo='PIX_MANUAL',valor_cents=4990,status='PENDENTE'))
        db.commit()
    s.processar_um();post.assert_not_called()
    with a[2]() as db:
        assert db.query(m.AcessoCurso).filter_by(ativo=True).count()==1
        assert db.query(m.ContratacaoCurso).count()==1
