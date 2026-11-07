"""Correções da Fase 2: somente Storage em memória e banco isolado."""
from datetime import datetime, timedelta, timezone
import base64
import json
from threading import Event
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import patch
from contextlib import nullcontext

import pytest
from fastapi import HTTPException
from app import models as m
from app.imagens_storage import SupabaseImagens
from app.imagens_manutencao import limpar_pendentes, reconciliar_objetos, ManutencaoImagens
from test_imagens_teoria import ambiente_imagens, aulas, infraestrutura, enviar, salvar, png


def jwt(papel):
    return 'eyJhbGciOiJIUzI1NiJ9.'+base64.urlsafe_b64encode(json.dumps({'role':papel}).encode()).decode().rstrip('=')+'.sintetica'


@pytest.mark.parametrize('moderna,variavel', [(True,'SUPABASE_SECRET_KEY'), (True,'SUPABASE_SERVICE_ROLE_KEY'), (False,'SUPABASE_SERVICE_ROLE_KEY')])
def test_cabecalhos_upload_assinatura_listagem_exclusao(monkeypatch,moderna,variavel):
    for nome in ['SUPABASE_SECRET_KEY','SUPABASE_SERVICE_ROLE_KEY']:
        monkeypatch.delenv(nome,raising=False)
    chave='sb_secret_chave_sintetica_de_teste_1234' if moderna else jwt('service_role')
    monkeypatch.setenv(variavel,chave)
    monkeypatch.setenv('SUPABASE_URL','https://exemplo-teste.supabase.co')
    monkeypatch.setenv('SUPABASE_IMAGENS_BUCKET','teoria-imagens')
    chamadas=[]
    class Sessao:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def request(self,metodo,url,**kwargs):
            headers=kwargs['headers']
            assert headers['apikey']==chave
            assert ('Authorization' not in headers) if moderna else headers['Authorization']=='Bearer '+chave
            assert self.trust_env is False and kwargs['allow_redirects'] is False
            chamadas.append((metodo,url,kwargs))
            return SimpleNamespace(status_code=200,json=lambda:[] if '/list/' in url else {'signedURL':'/object/sign/teoria-imagens/a.png?token=simulado'})
    monkeypatch.setattr('app.imagens_storage.requests.Session',Sessao)
    storage=SupabaseImagens()
    storage.enviar('a.png',b'pixels','image/png');storage.assinar('a.png')
    assert storage.listar(100,50)==[]
    storage.excluir('a.png')
    assert [c[0] for c in chamadas]==['POST','POST','POST','DELETE']
    assert chamadas[2][2]['json']=={'prefix':'','limit':50,'offset':100,'sortBy':{'column':'name','order':'asc'}}


@pytest.mark.parametrize('chave', ['sb_publishable_chave_sintetica','sb_secret_',jwt('anon'),jwt('authenticated'),'invalida','a.W10.b'])
def test_chaves_publicas_ou_invalidas_recusadas_sem_expor_chave(monkeypatch,chave):
    monkeypatch.setenv('SUPABASE_URL','https://exemplo-teste.supabase.co')
    monkeypatch.setenv('SUPABASE_SECRET_KEY',chave)
    with pytest.raises(HTTPException) as erro:SupabaseImagens()
    assert erro.value.status_code==503 and chave not in erro.value.detail


class ListagemMemoria:
    bucket='teoria-imagens-teste'
    def __init__(self,base):
        self.base=base;self.datas={};self.falhar=set();self.tentativas=[]
    def adicionar(self,chave,idade=48,**campos):
        self.base.objetos[chave]=(png(),'image/png')
        data=(datetime.now(timezone.utc)-timedelta(hours=idade)).isoformat()
        self.datas[chave]={'name':chave,'created_at':data,'updated_at':data,**campos}
    def listar(self,offset,limite):
        return [self.datas[k] for k in sorted(self.base.objetos)][offset:offset+limite]
    def excluir(self,chave):
        self.tentativas.append(chave)
        if chave in self.falhar:raise HTTPException(502,'Falha simulada')
        self.base.excluir(chave)


def envelhecer(factory,ids):
    with factory() as db:
        for id in ids:db.get(m.ImagemTeoria,id).ultima_atividade=datetime.utcnow()-timedelta(days=2)
        db.commit()


def test_pendentes_limpeza_preserva_referencias_e_libera_cota(ambiente_imagens):
    _,c,factory,_,base=ambiente_imagens
    imgs=enviar(c,png(),png(),png())
    assert salvar(c,imgs[0]).status_code==200
    # Defesa contra associação ausente: material ainda contém referência canônica.
    assert salvar(c,imgs[1]).status_code==200
    with factory() as db:
        db.query(m.ImagemTeoriaMaterial).filter_by(imagem_id=imgs[1]['id']).delete();db.commit()
    envelhecer(factory,[i['id'] for i in imgs])
    storage=ListagemMemoria(base)
    for chave in base.objetos.copy():storage.adicionar(chave)
    with factory() as db:
        assert limpar_pendentes(db,storage)==1
        assert limpar_pendentes(db,storage)==0
        assert db.query(m.ImagemTeoria).count()==2
    assert len(base.objetos)==2


def test_compensacao_falha_reconciliada_e_retry_idempotente(ambiente_imagens):
    _,c,factory,_,base=ambiente_imagens
    img=enviar(c)[0];envelhecer(factory,[img['id']])
    chave=next(iter(base.objetos));storage=ListagemMemoria(base);storage.adicionar(chave)
    storage.falhar.add(chave)
    with factory() as db:
        assert limpar_pendentes(db,storage)==1
        assert db.get(m.ImagemTeoria,img['id']) is None
        assert chave in base.objetos
        assert reconciliar_objetos(db,storage)['apagados']==0
        storage.falhar.clear()
        assert reconciliar_objetos(db,storage)['apagados']==1
        assert reconciliar_objetos(db,storage)['apagados']==0
    assert not base.objetos


def test_falha_commit_nao_exclui_objeto(ambiente_imagens):
    _,c,factory,_,base=ambiente_imagens
    img=enviar(c)[0];envelhecer(factory,[img['id']])
    storage=ListagemMemoria(base)
    with factory() as db,patch.object(db,'commit',side_effect=RuntimeError('Falha SQL simulada')):
        with pytest.raises(RuntimeError):limpar_pendentes(db,storage)
        db.rollback()
        assert db.get(m.ImagemTeoria,img['id']) is not None
    assert len(base.objetos)==1 and not storage.tentativas


def test_orfaos_paginacao_carencia_dados_invalidos_e_lock(ambiente_imagens):
    _,c,factory,_,base=ambiente_imagens
    img=enviar(c)[0];assert salvar(c,img).status_code==200
    storage=ListagemMemoria(base)
    for chave in base.objetos.copy():storage.adicionar(chave)
    antigos=[str(uuid4())+'.png' for _ in range(7)]
    for chave in antigos:storage.adicionar(chave)
    recentes=str(uuid4())+'.webp';storage.adicionar(recentes,idade=1)
    semdata=str(uuid4())+'.png';storage.adicionar(semdata,created_at=None)
    atualizado=str(uuid4())+'.jpg';storage.adicionar(atualizado,updated_at=datetime.now(timezone.utc).isoformat())
    alheio='arquivo-outro-sistema.png';storage.adicionar(alheio)
    offset=0;apagados=0
    with factory() as db:
        for _ in range(20):
            r=reconciliar_objetos(db,storage,offset=offset,tamanho_pagina=2,max_paginas=1)
            apagados+=r['apagados'];offset=r['offset']
            if r['concluido']:break
        assert apagados==7
        assert {recentes,semdata,atualizado,alheio}.issubset(base.objetos)
        assert db.get(m.ImagemTeoria,img['id']).chave in base.objetos
        assert reconciliar_objetos(db,storage)['apagados']==0
        ocupada=str(uuid4())+'.png';storage.adicionar(ocupada)
        with patch('app.imagens_manutencao.travar_objeto',return_value=False):
            assert reconciliar_objetos(db,storage)['apagados']==0
        assert ocupada in base.objetos


def test_orfao_referenciado_no_html_sem_metadados_nunca_excluido(ambiente_imagens):
    _,_,factory,_,base=ambiente_imagens
    id=str(uuid4());storage=ListagemMemoria(base);storage.adicionar(id+'.png')
    with factory() as db:
        material=db.get(m.Material,1);material.conteudo_formato='html_v1';material.conteudo='<img src="/midias/imagens/'+id+'">';db.commit()
        assert reconciliar_objetos(db,storage)['apagados']==0
    assert id+'.png' in base.objetos


def test_executor_automatico_reinicia_apos_falha_e_encerra(monkeypatch):
    monkeypatch.setenv('AMBIENTE_TESTE','0');monkeypatch.setenv('IMAGENS_MANUTENCAO_ATIVA','true')
    worker=ManutencaoImagens(SimpleNamespace(dialect=SimpleNamespace(name='postgresql')),None)
    feitas=[];fim=Event()
    def ciclo():
        feitas.append(True)
        if len(feitas)==1:raise RuntimeError('Falha simulada sem dados reais')
        worker.parar.set();fim.set()
    worker.ciclo=ciclo
    # Somente no teste, evitar aguardar o intervalo operacional de 5 minutos.
    with patch.object(worker.parar,'wait',return_value=False):
        worker.iniciar();assert fim.wait(2);worker.encerrar()
    assert len(feitas)==2 and not worker.thread.is_alive()
    monkeypatch.setenv('IMAGENS_MANUTENCAO_ATIVA','false')
    desativado=ManutencaoImagens(None,None);desativado.iniciar()
    assert desativado.thread is None


def test_listagem_invalida_falha_fechada(monkeypatch):
    monkeypatch.setenv('SUPABASE_URL','https://exemplo-teste.supabase.co')
    monkeypatch.setenv('SUPABASE_SECRET_KEY','sb_secret_chave_sintetica_de_teste_1234')
    storage=SupabaseImagens()
    with patch.object(storage,'_request',return_value=SimpleNamespace(json=lambda:{'erro':'simulado'})):
        with pytest.raises(HTTPException):storage.listar()


def test_ciclo_automatico_libera_limite_de_cem_pendencias(ambiente_imagens):
    _,c,factory,_,base=ambiente_imagens
    storage=ListagemMemoria(base)
    with factory() as db:
        for _ in range(100):
            id=str(uuid4());chave=id+'.png';storage.adicionar(chave)
            db.add(m.ImagemTeoria(id=id,chave=chave,autor_id=1,mime='image/png',tamanho=10,
                largura=90,altura=40,sha256='0'*64,ultima_atividade=datetime.utcnow()-timedelta(days=2)))
        db.commit()
    assert c.post('/admin/imagens/arquivos',files=[('arquivos',('a.png',png(),'image/png'))]).status_code==429
    worker=ManutencaoImagens(factory.kw['bind'],factory,storage_factory=lambda:storage)
    # SQLite simula dados; advisory locks reais têm teste próprio em PostgreSQL.
    with patch('app.imagens_manutencao.exclusao_mutua',return_value=nullcontext(True)):
        worker.ciclo()
    assert not base.objetos
    assert len(enviar(c))==1


def test_previa_renova_rascunho_ativo_antes_da_limpeza(ambiente_imagens):
    _,c,factory,_,base=ambiente_imagens
    img=enviar(c)[0];envelhecer(factory,[img['id']])
    assert c.post('/admin/imagens/assinaturas',json={'ids':[img['id']]}).status_code==200
    with factory() as db:
        assert limpar_pendentes(db,base)==0
        assert db.get(m.ImagemTeoria,img['id']).ultima_atividade>datetime.utcnow()-timedelta(minutes=1)
