"""Auditoria/migration/corridas em PostgreSQL local compras_test_* descartável."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import patch
import psycopg
import pytest
from sqlalchemy import select,text,update
from sqlalchemy.exc import SQLAlchemyError
from app import models as m
from app.pausa_financeira import Protecao,Isolamento,inbox,isolamentos,IDS_HISTORICOS
from test_compras_concorrencia_pg import motor
from test_compras_fluxo import ambiente_compra
from test_isolamento_historico import historicos,isolar,snapshot
from test_pausa_financeira import modo,enviar

SQL=Path(__file__).parent/'migrations/018_isolamento_notificacoes_historicas.sql'

def aplicar(engine):
    with engine.connect() as c:c.connection.driver_connection.execute(SQL.read_text())


def test_migration_idempotente_preserva_dados_e_rls(ambiente_compra,motor):
    a=ambiente_compra;body=historicos(a);antes=snapshot(a)
    assert isolar(a,body).status_code==200
    with motor.connect() as c:audit=c.execute(select(isolamentos)).all()
    aplicar(motor)
    with motor.connect() as c:
        assert c.execute(select(isolamentos)).all()==audit
        assert c.execute(text("SELECT relrowsecurity FROM pg_class WHERE oid='notificacoes_mp_isolamentos'::regclass")).scalar()
        assert c.execute(text("SELECT count(*) FROM pg_policy WHERE polrelid='notificacoes_mp_isolamentos'::regclass")).scalar()==0
        assert c.execute(text('SELECT modo,geracao FROM controle_financeiro')).one()==('RECUPERACAO',2)
    assert snapshot(a)==antes
    with a[2]() as db:assert db.query(m.Pagamento).count()==0
    with pytest.raises(SQLAlchemyError):
        with motor.begin() as c:
            c.execute(text("INSERT INTO notificacoes_mp_isolamentos(notificacao_id,isolada_por,geracao,motivo) VALUES(5,2,2,'fora do escopo')"))
    with pytest.raises(SQLAlchemyError):
        with motor.begin() as c:
            c.execute(text("INSERT INTO notificacoes_mp_isolamentos(notificacao_id,isolada_por,geracao,motivo) VALUES(11,2,2,'novo evento')"))


@pytest.mark.parametrize('objeto',['coluna','check','fk','politica'])
def test_migration_incompatibilidade_interrompe(ambiente_compra,motor,objeto):
    with motor.begin() as c:
        if objeto=='coluna':c.execute(text('ALTER TABLE notificacoes_mp_isolamentos ALTER COLUMN motivo TYPE text'))
        if objeto=='check':c.execute(text('ALTER TABLE notificacoes_mp_isolamentos DROP CONSTRAINT ck_isolamento_ids'))
        if objeto=='fk':c.execute(text('ALTER TABLE notificacoes_mp_isolamentos DROP CONSTRAINT fk_isolamento_admin'))
        if objeto=='politica':c.execute(text('CREATE POLICY indevida ON notificacoes_mp_isolamentos USING(true)'))
    with pytest.raises(psycopg.Error):aplicar(motor)
    with motor.connect() as c:assert c.execute(text('SELECT modo,geracao FROM controle_financeiro')).one()==('NORMAL',0)


def test_dois_administradores_preservam_primeira_auditoria(ambiente_compra,motor):
    a=ambiente_compra;body=historicos(a);p=a[0].app.state.protecao_financeira
    outra=Protecao(motor,a[2],p.processor,consulta=p.consulta)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda prot:prot.auditar_isolamento(Isolamento(**body),2),(p,outra)))
    assert all(r['ids']==list(IDS_HISTORICOS) for r in results)
    with motor.connect() as c:assert len(c.execute(select(isolamentos)).all())==8


def test_isolamento_enquanto_consulta_em_andamento_nao_processa(ambiente_compra,motor):
    a=ambiente_compra;body=historicos(a);p=a[0].app.state.protecao_financeira
    outra=Protecao(motor,a[2],p.processor,consulta=p.consulta)
    consultando=Event();liberar=Event();antes=snapshot(a)
    def consulta(pid):
        consultando.set();assert liberar.wait(8)
        return object()
    with patch.object(p,'consulta',side_effect=consulta),patch.object(p,'processor') as processador:
        with ThreadPoolExecutor(max_workers=2) as pool:
            tarefa=pool.submit(p.processar,1,True)
            assert consultando.wait(5)
            assert outra.auditar_isolamento(Isolamento(**body),2)['ids']==list(IDS_HISTORICOS)
            liberar.set();assert not tarefa.result(timeout=8)['processado']
        processador.assert_not_called()
    assert snapshot(a)==antes


def test_falha_de_consulta_concorrente_nao_altera_evento_isolado(ambiente_compra,motor):
    a=ambiente_compra;body=historicos(a);p=a[0].app.state.protecao_financeira
    outra=Protecao(motor,a[2],p.processor,consulta=p.consulta)
    consultando=Event();liberar=Event();antes=snapshot(a)
    def consulta(pid):
        consultando.set();assert liberar.wait(8)
        raise RuntimeError('falha simulada')
    with patch.object(p,'consulta',side_effect=consulta):
        with ThreadPoolExecutor(max_workers=2) as pool:
            tarefa=pool.submit(p.processar,1,True);assert consultando.wait(5)
            outra.auditar_isolamento(Isolamento(**body),2)
            liberar.set();assert not tarefa.result(timeout=8)['processado']
    assert snapshot(a)==antes


def test_isolamento_aguarda_processador_e_nao_isola_evento_concluido(ambiente_compra,motor):
    from test_transacoes_mp import preparar
    from fastapi import HTTPException
    from time import monotonic, sleep
    a=ambiente_compra;pid,_,_,_=preparar(a)
    body=historicos(a);p=a[0].app.state.protecao_financeira
    outra=Protecao(motor,a[2],p.processor,consulta=p.consulta)
    gravou=Event();liberar=Event()
    def processor(tx,db,**kwargs):
        db.get(m.Pagamento,pid).status='CANCELLED'
        db.commit()  # Flush somente; barreira permanece na transação.
        gravou.set();assert liberar.wait(8)
        return {'ok':True,'status':'CANCELLED'}
    def isolar_concorrente():
        try:return outra.auditar_isolamento(Isolamento(**body),2)
        except HTTPException as exc:return exc.status_code
    with patch.object(p,'consulta',return_value=object()),patch.object(p,'processor',side_effect=processor):
        with ThreadPoolExecutor(max_workers=2) as pool:
            processando=pool.submit(p.processar,1,True)
            assert gravou.wait(5)
            isolando=pool.submit(isolar_concorrente)
            try:
                fim=monotonic()+3
                while monotonic()<fim:
                    with motor.connect() as c:
                        espera=c.execute(text("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND wait_event_type='Lock' AND query LIKE '%controle_financeiro%'")).scalar()
                    if espera:break
                    sleep(.02)
                assert espera and not isolando.done()
            finally:liberar.set()
            assert processando.result(timeout=8)['processado']
            assert isolando.result(timeout=8)==409
    with motor.connect() as c:
        assert c.execute(select(isolamentos)).all()==[]
        assert c.execute(select(inbox.c.estado).where(inbox.c.id==1)).scalar_one()=='CONCLUIDO'
        assert c.execute(select(inbox.c.estado).where(inbox.c.id==2)).scalar_one()=='ERRO'
    with a[2]() as db:
        assert db.get(m.Pagamento,pid).status=='CANCELLED'
        assert db.query(m.ContratacaoCurso).count()==0


def test_018_sem_grants_publicos_nem_politicas(ambiente_compra,motor):
    with motor.connect() as c:
        assert not c.execute(text("SELECT EXISTS (SELECT FROM pg_class t CROSS JOIN LATERAL aclexplode(coalesce(t.relacl,acldefault('r',t.relowner))) a WHERE t.oid='notificacoes_mp_isolamentos'::regclass AND a.grantee=0)")).scalar()
        assert c.execute(text("SELECT count(*) FROM pg_trigger WHERE tgrelid='notificacoes_mp_isolamentos'::regclass AND NOT tgisinternal")).scalar()==0
        assert c.execute(text('SHOW server_version')).scalar().startswith('17.6')


# Mesmos testes HTTP reais, agora com conexões e constraints PostgreSQL.
from test_isolamento_historico import test_nova_venda_apos_isolamento_pendente_aprovada_idempotente


def test_reabertura_aguarda_isolamento_atomico(ambiente_compra,motor):
    from fastapi import HTTPException
    from sqlalchemy import event
    from app.pausa_financeira import Modo
    from time import monotonic, sleep
    a=ambiente_compra;body=historicos(a);p=a[0].app.state.protecao_financeira
    outra=Protecao(motor,a[2],p.processor,consulta=p.consulta)
    inserindo=Event();liberar=Event()
    def segurar(c,cursor,sql,params,context,many):
        if sql.lstrip().startswith('INSERT INTO notificacoes_mp_isolamentos') and not inserindo.is_set():
            inserindo.set();assert liberar.wait(8)
    def normal():
        return outra.mudar(Modo(modo='NORMAL',geracao=2,motivo='retomada teste',conferencia_provedor=True),2)
    event.listen(motor,'before_cursor_execute',segurar)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            isolando=pool.submit(p.auditar_isolamento,Isolamento(**body),2)
            assert inserindo.wait(5)
            reabrindo=pool.submit(normal)
            try:
                fim=monotonic()+3;espera=0
                while monotonic()<fim:
                    with motor.connect() as c:
                        espera=c.execute(text("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND wait_event_type='Lock' AND query LIKE '%controle_financeiro%'")).scalar()
                    if espera:break
                    sleep(.02)
                assert espera and not reabrindo.done()
            finally:liberar.set()
            assert isolando.result(timeout=8)['ids']==list(IDS_HISTORICOS)
            assert reabrindo.result(timeout=8)['modo']=='NORMAL'
    finally:event.remove(motor,'before_cursor_execute',segurar)
    with motor.connect() as c:
        assert len(c.execute(select(isolamentos)).all())==8
        assert c.execute(text('SELECT modo,geracao FROM controle_financeiro')).one()==('NORMAL',3)


def test_rls_bloqueia_papel_nao_privilegiado_mesmo_com_grant(ambiente_compra,motor):
    a=ambiente_compra;body=historicos(a);assert isolar(a,body).status_code==200
    with motor.begin() as c:
        c.execute(text('CREATE ROLE cliente_isolamento_test NOLOGIN'))
        c.execute(text('GRANT USAGE ON SCHEMA public TO cliente_isolamento_test'))
        c.execute(text('GRANT SELECT, INSERT, UPDATE ON notificacoes_mp_isolamentos TO cliente_isolamento_test'))
    try:
        with motor.begin() as c:
            c.execute(text('SET LOCAL ROLE cliente_isolamento_test'))
            assert c.execute(select(isolamentos)).all()==[]
            assert c.execute(update(isolamentos).values(motivo='não alterar')).rowcount==0
        with pytest.raises(SQLAlchemyError):
            with motor.begin() as c:
                c.execute(text('SET LOCAL ROLE cliente_isolamento_test'))
                c.execute(text("INSERT INTO notificacoes_mp_isolamentos(notificacao_id,isolada_por,geracao,motivo) VALUES(1,2,2,'não inserir')"))
    finally:
        with motor.begin() as c:
            c.execute(text('REVOKE ALL ON notificacoes_mp_isolamentos FROM cliente_isolamento_test'))
            c.execute(text('REVOKE ALL ON SCHEMA public FROM cliente_isolamento_test'))
            c.execute(text('DROP ROLE cliente_isolamento_test'))
