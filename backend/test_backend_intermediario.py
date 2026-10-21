"""Valida a exportação real em subprocesso e SQLite isolado, sem executar migrations."""
import ast
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
# Base revisada; permanece explícita mesmo após o commit intermediário.
BASE_SHA = 'c42eb6a919b1da1bf1ab578a3d036543aeaa4d71'
CHILD = r'''
import hashlib, hmac, importlib.util, os, sys, types, unittest, ast
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select, text, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool, QueuePool
import dotenv
from app import models as m
from app.pausa_financeira import metadata, controle, inbox, agora
from app.financeiro_transacional import configuracao_pool
MAIN_PATH = sys.argv[1]

def audit(event, args):
    if event in {'socket.connect', 'socket.connect_ex'}:
        raise AssertionError('Conexão externa proibida nesta validação')
sys.addaudithook(audit)

class Exportado(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
        @event.listens_for(self.engine,'connect')
        def sqlite_compat(c, record):
            c.create_function('BTRIM',1,lambda v:v.strip() if v is not None else None)
        tabelas={modelo.__table__ for modelo in (m.Usuario,m.Curso,m.TempoAcessoCurso,
            m.ContratacaoCurso,m.DemonstracaoCurso,m.AcessoCurso,m.Vendedor,m.CupomDesconto,
            m.OportunidadeCompra,m.Pagamento,m.PeriodoAcessoPagamento,m.ConcessaoAcessoAdmin,
            m.ReembolsoFinanceiro,m.ContestacaoPagamento)}
        while True:
            deps={fk.column.table for tabela in tabelas for fk in tabela.foreign_keys}
            if deps <= tabelas:break
            tabelas |= deps
        # DDL exclusivo da fixture SQLite: nenhum arquivo SQL de migration executado.
        m.Base.metadata.create_all(self.engine,tables=list(tabelas))
        metadata.create_all(self.engine)
        with self.engine.begin() as c:
            c.execute(controle.insert().values(id=1,modo='NORMAL',geracao=0,
                alterado_em=agora(),motivo='fixture isolada'))
        self.factory=sessionmaker(bind=self.engine,autoflush=False)
        with self.factory() as db:
            db.add(m.Usuario(id=1,nome='Teste',email='aluno@teste.local',senha_hash='teste',
                cpf='1',telefone='0',is_admin=False))
            db.add(m.Curso(id=1,nome='Curso teste',ativo=True));db.flush()
            db.add(m.TempoAcessoCurso(id=1,curso_id=1,meses=4,valor_cents=4990,ativo=True));db.commit()
        stub=types.ModuleType('app.database');stub.engine=self.engine;stub.SessionLocal=self.factory
        spec=importlib.util.spec_from_file_location('app.main',MAIN_PATH)
        self.main=importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules,{'app.database':stub}),patch.object(dotenv,'load_dotenv',return_value=False):
            spec.loader.exec_module(self.main)
        self.main.MP_ACCESS_TOKEN='simulado';self.main.MP_WEBHOOK_SECRET='segredo-teste'
        self.main.app.dependency_overrides[self.main.get_usuario_atual]=lambda:types.SimpleNamespace(
            id=1,email='aluno@teste.local',is_admin=True)
        resp=Mock(status_code=201);resp.json.return_value={'id':'pref_simulada','init_point':'https://example.invalid'}
        self.post=patch.object(self.main.requests,'post',return_value=resp).start()
        self.get=patch.object(self.main.requests,'get',return_value=resp).start()
        self.client=TestClient(self.main.app);self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None,None,None);patch.stopall();self.engine.dispose()

    def pausar(self):
        r=self.client.post('/admin/financeiro/manutencao',json={
            'modo':'PAUSADO','geracao':0,'motivo':'teste'})
        self.assertEqual(r.status_code,200,r.text)

    def webhook(self, valido=True):
        manifest='id:101;request-id:teste;ts:1234567890;'
        mac=hmac.new(b'segredo-teste',manifest.encode(),hashlib.sha256).hexdigest()
        return self.client.post('/webhooks/mercadopago?type=payment&data.id=101',
            headers={'x-request-id':'teste','x-signature':f'ts=1234567890,v1={mac if valido else "invalido"}'},
            json={'id':'evento-teste','type':'payment','data':{'id':'101'}})

    def test_versao_sem_colunas_014015(self):
        r=self.client.get('/admin/financeiro/manutencao');self.assertEqual(r.status_code,200,r.text)
        self.assertFalse(r.json()['backend_definitivo'])
        self.assertEqual(r.json()['versao_protecao'],'pausa-financeira-v2-transacional')
        colunas={c['name'] for c in inspect(self.engine).get_columns('pagamentos')}
        self.assertTrue({'mp_status','pagamento_origem_id'}.isdisjoint(colunas))
        self.assertNotIn('confirmado_por',{c['name'] for c in inspect(self.engine).get_columns('reembolsos_financeiros')})

    def test_pausa_bloqueia_rotas_sem_chamadas_externas(self):
        self.pausar()
        for path in ('/checkout/mercadopago','/pagamentos/confirmar','/admin/pagamentos/revalidar',
            '/me/reembolso/1','/admin/reembolsos/1/aprovar','/admin/reembolsos/1/recusar',
            '/admin/reembolsos/1/pix-manual','/admin/reembolsos/1/pix-manual/confirmar',
            '/admin/acessos','/cursos/1/demonstracao'):
            with self.subTest(path=path):self.assertEqual(self.client.post(path,json={}).status_code,503)
        self.post.assert_not_called();self.get.assert_not_called()
        with self.factory() as db:self.assertEqual(db.query(m.Pagamento).count(),0)

    def test_webhook_pausado_duravel_repetido_e_assinatura(self):
        self.pausar()
        self.assertEqual(self.webhook(False).status_code,401)
        for _ in range(2):
            r=self.webhook();self.assertEqual(r.status_code,200,r.text)
            self.assertTrue(r.json()['armazenado']);self.assertFalse(r.json()['processado'])
        with self.engine.connect() as c:
            self.assertEqual(len(c.execute(select(inbox)).all()),1)
        self.get.assert_not_called();self.post.assert_not_called()

    def test_recuperacao_definitiva_bloqueada(self):
        self.pausar()
        self.assertEqual(self.client.post('/admin/financeiro/manutencao',json={
            'modo':'RECUPERACAO','geracao':1,'motivo':'teste'}).status_code,409)
        self.assertEqual(self.client.post('/admin/financeiro/notificacoes/recuperar',json={'limite':1}).status_code,409)
        self.assertEqual(self.client.post('/admin/financeiro/notificacoes/reconciliar',json={
            'inicio':'2026-10-10T00:00:00Z','fim':'2026-10-11T00:00:00Z','pagina':0}).status_code,503)

    def test_checkout_em_esquema_antigo(self):
        r=self.client.post('/checkout/mercadopago',json={'tempo_acesso_id':1})
        self.assertEqual(r.status_code,200,r.text)
        with self.factory() as db:
            p=db.query(m.Pagamento).one()
            self.assertEqual(p.status,'PENDENTE');self.assertEqual(p.mp_preference_id,'pref_simulada')
            self.assertEqual(db.query(m.ContratacaoCurso).count(),0)
        self.assertEqual(self.post.call_count,1)

    def test_checkout_incerto_nao_reenvia(self):
        self.post.return_value.status_code=500;self.post.return_value.text='simulado'
        self.assertEqual(self.client.post('/checkout/mercadopago',json={'tempo_acesso_id':1}).status_code,502)
        with self.factory() as db:
            self.assertEqual(db.query(m.Pagamento).one().status,'CHECKOUT_INDEFINIDO')
            self.assertEqual(db.query(m.ContratacaoCurso).count(),0)
        self.assertEqual(self.client.post('/checkout/mercadopago',json={'tempo_acesso_id':1}).status_code,409)
        self.assertEqual(self.post.call_count,1)

    def test_pool_real_cinco_sem_overflow(self):
        for key in ('DB_POOL_SIZE','DB_MAX_OVERFLOW','DB_POOL_TIMEOUT_S'):os.environ.pop(key,None)
        # Avaliar só a expressão create_engine do ramo cloud do arquivo exportado.
        # Não importar database.py nem executar seu create_all/startup.
        from pathlib import Path
        tree=ast.parse(Path(MAIN_PATH).with_name('database.py').read_text())
        branch=next(n for n in tree.body if isinstance(n,ast.If) and
                    isinstance(n.test,ast.Name) and n.test.id=='is_cloud')
        call=next(n.value for n in branch.body if isinstance(n,ast.Assign))
        engine=eval(compile(ast.Expression(call),'<pool exportado>','eval'),{
            'create_engine':create_engine,'configuracao_pool':configuracao_pool,
            'DATABASE_URL':'postgresql+psycopg://teste:teste@invalid.invalid/teste'})
        try:
            self.assertEqual(engine.pool.size(),5);self.assertEqual(engine.pool._max_overflow,0)
            self.assertEqual(engine.pool.timeout(),3)
        finally:engine.dispose()

sys.argv=[sys.argv[0]]
unittest.main(verbosity=2)
'''
class PreparadorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="resumao-intermediario-test-")
        cls.dest = Path(cls.temp.name)/"exportacao"
        cls.env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        subprocess.run([sys.executable,str(ROOT/'backend/preparar_backend_pausa.py'),
            '--destino',str(cls.dest),'--origem',BASE_SHA],cwd=ROOT,env=cls.env,check=True,capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_modelos_schemas_preservados_sem_frontend(self):
        for name in ('models.py','schemas.py'):
            original=subprocess.check_output(['git','show',BASE_SHA+':backend/app/'+name],cwd=ROOT)
            self.assertEqual((self.dest/'backend/app'/name).read_bytes(),original)
        self.assertFalse((self.dest/'site-html').exists())
        self.assertFalse((self.dest/'backend/app/transacoes_mp.py').exists())
        for n in ('014_pagamentos_multiplas_transacoes.sql','015_reembolsos_manual_auditoria.sql'):
            self.assertFalse((self.dest/'backend/migrations'/n).exists())

    def test_sintaxe_e_dependencias(self):
        for p in (self.dest/'backend/app').glob('*.py'):ast.parse(p.read_text())
        main=(self.dest/'backend/app/main.py').read_text()
        self.assertIn('definitivo=False',main)
        self.assertNotIn('from app.transacoes_mp',main)
        self.assertIn('**configuracao_pool()', (self.dest/'backend/app/database.py').read_text())

    def test_nao_sobrescreve_destino(self):
        antes=(self.dest/'backend/app/main.py').read_bytes()
        result=subprocess.run([sys.executable,str(ROOT/'backend/preparar_backend_pausa.py'),
            '--destino',str(self.dest),'--origem',BASE_SHA],cwd=ROOT,env=self.env,capture_output=True)
        self.assertNotEqual(result.returncode,0)
        self.assertEqual((self.dest/'backend/app/main.py').read_bytes(),antes)

    def test_backend_exportado_em_processo_isolado(self):
        env=dict(self.env,PYTHONPATH=str(self.dest/'backend'),AMBIENTE_TESTE='1',
                 DATABASE_URL='sqlite://',RENDER_GIT_COMMIT='sha-simulado')
        result=subprocess.run([sys.executable,'-c',CHILD,str(self.dest/'backend/app/main.py')],
            env=env,cwd=self.dest,capture_output=True,text=True,timeout=40)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('Ran 7 tests',result.stderr)


if __name__ == '__main__':
    unittest.main()
