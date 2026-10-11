"""Servidor temporário sem aplicação, banco ou processamento financeiro."""
import json
import os
import signal
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HEALTH_PATHS = frozenset({"/", "/__maintenance_health"})
BODY = json.dumps({"detail": "Serviço temporariamente indisponível para manutenção."},
                  ensure_ascii=False).encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    # HTTP/1.0 e Connection: close: não manter conexões/corpos pendentes.
    protocol_version = "HTTP/1.0"
    server_version = "Maintenance"
    sys_version = ""

    def setup(self):
        self.request.settimeout(5)
        super().setup()

    def handle(self):
        try:
            super().handle()
        except OSError:
            # Cliente encerrou/resetou a conexão ou excedeu o timeout.
            self.close_connection = True

    def responder(self):
        # BaseHTTPRequestHandler normaliza "//" para "/"; conferir o alvo original.
        alvo = self.requestline.split()[1]
        saudavel = self.command in {"GET", "HEAD"} and alvo in HEALTH_PATHS
        body = b'{"status":"maintenance"}' if saudavel else BODY
        self.send_response(200 if saudavel else 503)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        if not saudavel:
            self.send_header("Retry-After", "60")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)
        self.close_connection = True

    # Inclui métodos desconhecidos: nenhuma rota válida cai em 200/501 por engano.
    def __getattr__(self, name):
        if name.startswith("do_"):
            return self.responder
        raise AttributeError(name)

    def log_message(self, format, *args):
        # Não registrar URL, identificadores de pagamentos ou cabeçalhos.
        pass


class Server(ThreadingHTTPServer):
    daemon_threads = True
    # Limitar threads e memória mesmo com conexões lentas.
    def __init__(self, address):
        self.slots = threading.BoundedSemaphore(16)
        super().__init__(address, Handler)

    def process_request(self, request, address):
        if not self.slots.acquire(blocking=False):
            try:
                request.settimeout(1)
                request.sendall(b"HTTP/1.0 503 Service Unavailable\r\n"
                                b"Connection: close\r\nRetry-After: 60\r\n"
                                b"Content-Length: 0\r\n\r\n")
            except OSError:
                pass
            finally:
                self.shutdown_request(request)
            return
        try:
            super().process_request(request, address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.slots.release()


def main():
    # Única configuração lida: porta fornecida pelo Render. Nenhum dotenv.
    port = int(os.environ.get("PORT", "10000"))
    if not 0 <= port <= 65535:
        raise ValueError("PORT fora do intervalo permitido")
    with Server(("0.0.0.0", port)) as server:
        encerrando = threading.Event()

        def parar(signum, frame):
            if not encerrando.is_set():
                encerrando.set()
                # shutdown não pode rodar na thread de serve_forever.
                threading.Thread(target=server.shutdown, daemon=True).start()

        signal.signal(signal.SIGTERM, parar)
        signal.signal(signal.SIGINT, parar)
        print(f"Manutenção temporária ativa; porta {server.server_port}", flush=True)
        server.serve_forever(poll_interval=0.1)


if __name__ == "__main__":
    main()
