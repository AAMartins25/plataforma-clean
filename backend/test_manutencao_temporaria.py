"""HTTP real em processo separado; proíbe imports da aplicação e conexões externas."""
import concurrent.futures
import http.client
import json
import os
from pathlib import Path
import subprocess
import sys
import socket
import time
import unittest
import runpy

SCRIPT = Path(__file__).with_name("manutencao_temporaria.py")
BOOTSTRAP = r'''
import builtins, os, runpy, sys
original_import = builtins.__import__
proibidos = {'app', 'fastapi', 'sqlalchemy', 'psycopg', 'psycopg2', 'dotenv', 'asyncpg'}
def importar(name, *args, **kwargs):
    if name.split('.')[0] in proibidos:
        raise AssertionError('Import proibido')
    return original_import(name, *args, **kwargs)
builtins.__import__ = importar
def audit(event, args):
    if event in {'socket.connect', 'socket.connect_ex'}:
        raise AssertionError('Conexão de saída proibida')
    if event == 'open' and isinstance(args[0], (str, bytes)):
        if '.env' in str(args[0]):
            raise AssertionError('Leitura dotenv proibida')
sys.addaudithook(audit)
original_getitem = os._Environ.__getitem__
def obter(self, key):
    if key in {'DATABASE_URL', 'PGHOST', 'PGPASSWORD', 'PGUSER'}:
        raise AssertionError('Leitura de configuração PostgreSQL proibida')
    return original_getitem(self, key)
os._Environ.__getitem__ = obter
runpy.run_path(sys.argv[1], run_name='__main__')
print('GUARDAS_OK', flush=True)
'''


class ManutencaoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        env = dict(os.environ, PORT="0", PYTHONDONTWRITEBYTECODE="1",
                   DATABASE_URL="postgresql://invalid.invalid/nao_utilizar")
        cls.process = subprocess.Popen([sys.executable, "-u", "-c", BOOTSTRAP, str(SCRIPT)],
            env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        linha = cls.process.stdout.readline()
        if not linha.startswith("Manutenção temporária ativa; porta "):
            cls.process.terminate()
            _, erro = cls.process.communicate(timeout=5)
            raise AssertionError("Servidor não iniciou: " + erro)
        cls.port = int(linha.rsplit(" ", 1)[1])

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate()
        saida, erro = cls.process.communicate(timeout=5)
        if cls.process.returncode != 0 or erro or "GUARDAS_OK" not in saida:
            raise AssertionError("Encerramento/guardas falharam: " + erro)

    def request(self, method, path, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        try:
            conn.request(method, path, body=body)
            response = conn.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            conn.close()

    def test_health_get_head(self):
        for path in ("/", "/__maintenance_health"):
            for method in ("GET", "HEAD"):
                with self.subTest(method=method, path=path):
                    status, headers, body = self.request(method, path)
                    self.assertEqual(status, 200)
                    self.assertEqual(headers["Cache-Control"], "no-store")
                    if method == "HEAD":
                        self.assertEqual(body, b"")
                    else:
                        self.assertEqual(json.loads(body), {"status": "maintenance"})

    def test_health_nao_aceita_post_query_ou_variantes(self):
        for method, path in (("POST", "/__maintenance_health"),
                             ("POST", "/"), ("GET", "/?x=1"),
                             ("HEAD", "/?x=1"), ("GET", "//"),
                             ("GET", "/__maintenance_health?x=1"),
                             ("GET", "/__maintenance_health/")):
            with self.subTest(method=method, path=path):
                self.assertEqual(self.request(method, path)[0], 503)

    def test_webhooks_nunca_confirmados(self):
        for path in ("/webhooks/mercadopago", "/webhooks/mercadopago?data.id=123",
                     "/webhooks/mercadopago/", "/webhooks/mercadopago?type=payment"):
            with self.subTest(path=path):
                status, headers, body = self.request("POST", path, '{"type":"payment"}')
                self.assertEqual(status, 503)
                self.assertEqual(headers["Retry-After"], "60")
                self.assertEqual(headers["Connection"], "close")
                self.assertNotIn("ok", json.loads(body))

    def test_todas_rotas_e_metodos_indisponiveis(self):
        for method in ("GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "CUSTOM"):
            for path in ("/", "/health", "/checkout/mercadopago", "/pagamentos/confirmar",
                         "/login", "/auth/login", "/token", "/__maintenance_health",
                         "/admin/financeiro/manutencao", "/admin/reembolsos/1/pix-manual"):
                if method in ("GET", "HEAD") and path in ("/", "/__maintenance_health"):
                    continue
                with self.subTest(method=method, path=path):
                    self.assertEqual(self.request(method, path)[0], 503)

    def test_corpo_invalido_nao_processado(self):
        self.assertEqual(self.request("POST", "/webhooks/mercadopago", "invalid json")[0], 503)

    def test_concorrencia_health_e_webhooks(self):
        def consultar(i):
            return self.request("GET" if i % 2 == 0 else "POST",
                "/" if i % 2 == 0 else "/webhooks/mercadopago")[0]
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(consultar, range(40)))
        self.assertEqual(results, [200 if i % 2 == 0 else 503 for i in range(40)])

    def test_servidor_permanece_ativo_com_guardas(self):
        self.assertIsNone(self.process.poll())
        self.assertEqual(self.request("GET", "/__maintenance_health")[0], 200)

    def test_saturacao_retorna_503_e_recupera(self):
        clientes = []
        try:
            for _ in range(16):
                cliente = socket.create_connection(("127.0.0.1", self.port), timeout=3)
                clientes.append(cliente)
                # Cabeçalhos incompletos mantêm uma thread ocupada até fechar.
                cliente.sendall(b"GET / HTTP/1.1\r\n")
            time.sleep(.1)
            status, headers, _ = self.request("POST", "/webhooks/mercadopago")
            self.assertEqual(status, 503)
            self.assertEqual(headers["Retry-After"], "60")
        finally:
            for cliente in clientes:
                cliente.close()
        limite = time.monotonic() + 2
        while self.request("GET", "/")[0] != 200:
            self.assertLess(time.monotonic(), limite)
            time.sleep(.02)


class IntermediarioRootTests(unittest.TestCase):
    def test_get_root_do_backend_completo_sem_sql(self):
        # Reutiliza a fixture isolada existente, sem alterar app/main.py ou seus testes.
        script = runpy.run_path(str(SCRIPT.with_name("test_backend_intermediario.py")))["CHILD"]
        teste = '''
    def test_root_200_sem_sql(self):
        from sqlalchemy import event
        def proibir_sql(*args, **kwargs):
            raise AssertionError('GET / tentou consultar o banco')
        event.listen(self.engine, 'before_cursor_execute', proibir_sql)
        try:
            r=self.client.get('/')
            self.assertEqual(r.status_code,200,r.text)
            self.assertIn('mensagem',r.json())
        finally:
            event.remove(self.engine, 'before_cursor_execute', proibir_sql)

'''
        anchor = '    def test_versao_sem_colunas_014015(self):'
        self.assertIn(anchor, script)
        script = script.replace(anchor, teste + anchor, 1)
        # No definitivo, executar somente a prova de GET /; as premissas do
        # esquema intermediário continuam testadas na exportação própria.
        script = script.replace("unittest.main(verbosity=2)",
            "unittest.main(argv=[sys.argv[0], 'Exportado.test_root_200_sem_sql'], verbosity=2)")
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", AMBIENTE_TESTE="1",
                   PYTHONPATH=str(SCRIPT.parent), DATABASE_URL="sqlite://",
                   RENDER_GIT_COMMIT="sha-teste-isolado")
        result = subprocess.run([sys.executable, "-c", script,
            str(SCRIPT.parent / "app/main.py")], cwd=SCRIPT.parent,
            env=env, capture_output=True, text=True, timeout=40)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Ran 1 test", result.stderr)


if __name__ == "__main__":
    unittest.main()
