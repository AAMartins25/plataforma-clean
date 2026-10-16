"""Regressão de HTML anterior ao deploy + JS atual. Rede totalmente simulada.

PYTHONPATH=<playwright> PLAYWRIGHT_BROWSERS_PATH=<browsers> python test-carregamento-sessao.py
--codigo <ref> executa o mesmo teste com JS versionado (para provar falha anterior).
Artefatos ficam exclusivamente em --saida (padrão /tmp/resumao-carregamento).
"""
import argparse
import asyncio
import json
import mimetypes
import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent
ORIGIN = 'https://frontend.example.invalid'
API = 'plataforma-quality-backend.onrender.com'
OLD = '9772525a6ad193fdc8c7436ea9dfe2be41dcc4e1'
SIZES = [320, 360, 375, 390, 430, 768, 820, 1024, 1180, 1366, 1920]
NAMES = ['Ana Silva', 'Mariaaparecidadosantosdealbuquerque de Oliveira e Vasconcelos']
PARAMS = '?curso_id=1&disciplina_id=1&assunto_id=1&pasta_id=1&contratacao_id=7&curso_nome=Curso%20simulado'


def version(ref, path):
    return subprocess.check_output(['git', 'show', f'{ref}:site-html/{path}'], cwd=ROOT)


class Env:
    def __init__(self, old=False, name=NAMES[0], token='A', admin=False):
        self.old, self.name, self.token, self.admin = old, name, token, admin
        self.errors, self.calls, self.blocked = [], [], []
        self.status = 200
        self.session_delay = 0
        self.fail_session = False
        self.delay_login = None
        self.login_seen = asyncio.Event()
        self.login_token = 'LOGIN_NOVO'

    def fixture(self, path):
        d = {'id': 1, 'nome': 'Disciplina simulada', 'bloqueada': False, 'assuntos': [], 'baterias': []}
        a = {'id': 1, 'nome': 'Assunto simulado', 'bloqueada': False, 'bloqueado': False, 'baterias': []}
        c = {'id': 1, 'curso_id': 1, 'nome': 'Curso simulado', 'nome_curso': 'Curso simulado', 'ativo': True,
             'descricao': 'Simulado', 'disciplinas': [dict(d, assuntos=[a])],
             'contratacoes': [{'id': 7, 'origem': 'PAGAMENTO', 'data_fim': '2027-12-31T00:00:00'}], 'demonstracoes': []}
        if path == '/me':
            return {'id': 901, 'nome': self.name, 'is_admin': self.admin, 'is_vendedor': False, 'is_aluno': True}
        if path == '/me/cursos' or path == '/cursos' or path == '/cursos-publicos':
            return [c]
        if path.endswith('/disciplinas'): return [d]
        if path.endswith('/assuntos'): return [a]
        if path.endswith('/pastas'): return [{'id': 1, 'tipo': 'TEORIA', 'nome': 'Teoria'}]
        if path.endswith('/aulas'): return [{'id': 1, 'titulo': 'Aula simulada', 'ordem': 1}]
        if path.endswith('/materiais'): return [{'id': 1, 'tipo': 'TEXTO', 'titulo': 'Material', 'conteudo': 'Simulado'}]
        if path == '/cursos/1' or path.endswith('/desempenho'): return c
        return []

    async def route(self, route):
        req = route.request
        u = urlparse(req.url)
        if u.hostname == API:
            self.calls.append((u.path, req.method))
            if req.method == 'OPTIONS':
                return await route.fulfill(status=204, headers={'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': '*', 'Access-Control-Allow-Methods': '*'})
            if u.path in ['/login', '/register']:
                self.login_seen.set()
                if self.delay_login: await self.delay_login.wait()
                return await route.fulfill(json={'access_token': self.login_token}, headers={'Access-Control-Allow-Origin': '*'})
            if u.path.startswith(('/checkout/', '/pagamentos/')):
                return await route.fulfill(status=403, json={'detail': 'Financeiro bloqueado no teste'}, headers={'Access-Control-Allow-Origin': '*'})
            return await route.fulfill(status=self.status, json=self.fixture(u.path) if self.status == 200 else {'detail': 'Sessão inválida simulada'}, headers={'Access-Control-Allow-Origin': '*'})
        if u.hostname == 'frontend.example.invalid':
            path = u.path.lstrip('/') or 'index.html'
            f = ROOT / path
            if not f.is_file(): return await route.fulfill(status=404)
            if path == 'js/sessao.js':
                if self.fail_session: return await route.abort('failed')
                await asyncio.sleep(self.session_delay)
            data = version(OLD, path) if self.old and path.endswith('.html') else version(ARGS.codigo, path) if ARGS.codigo and path.endswith('.js') else f.read_bytes()
            return await route.fulfill(body=data, content_type=mimetypes.guess_type(path)[0] or 'application/octet-stream')
        self.blocked.append(req.url)
        await route.abort('blockedbyclient')

    async def create(self, browser, width=390):
        ctx = await browser.new_context(viewport={'width': width, 'height': 900}, has_touch=width < 1200, service_workers='block')
        await ctx.route('**/*', self.route)
        await ctx.add_init_script('''if(location.origin==='https://frontend.example.invalid' && !sessionStorage.getItem('seeded')) {
            sessionStorage.setItem('seeded','1');localStorage.clear();''' + (f"localStorage.setItem('access_token',{json.dumps(self.token)});" if self.token else '') + '}')
        page = await ctx.new_page()
        page.on('pageerror', lambda error: self.errors.append(str(error)))
        page.on('dialog', lambda dialog: dialog.accept())
        return ctx, page


async def settle(page):
    await page.wait_for_load_state('networkidle')
    await page.wait_for_timeout(100)


async def identity(page, name):
    first = name.split()[0].upper()
    await page.wait_for_function('(first) => document.querySelector("header summary")?.textContent === first', arg=first, timeout=5000)
    assert await page.locator('header .ro-identity').count() == 1
    # A API retorna o nome completo; a apresentação preserva primeiro + último nome.
    expanded = await page.locator('header .ro-identity-expanded').text_content()
    assert expanded == (name.split()[0] + ' ' + name.split()[-1]).upper()


async def clean(page):
    assert await page.evaluate('!localStorage.getItem("access_token") && !localStorage.getItem("me_cache")')
    assert not await page.locator('.ro-identity').count()
    assert not await page.locator('#nomeUsuarioLogadoGlobal[title],#nome_aluno_logado[title]').count()


async def main():
    results = []
    ARGS.saida.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(args=['--disable-background-networking', '--host-resolver-rules=MAP * ~NOTFOUND'])

        async def case(name, env, fn, file='cursos.html', width=390):
            if ARGS.filtro and not re.search(ARGS.filtro, name): return
            ctx, page = await env.create(browser, width)
            try:
                await page.goto(ORIGIN + '/' + file + PARAMS)
                await settle(page)
                await fn(env, ctx, page)
                assert not env.errors, env.errors
                results.append({'name': name, 'ok': True, 'api_mock_calls': len(env.calls)})
            except Exception as error:
                results.append({'name': name, 'ok': False, 'error': repr(error), 'js_errors': env.errors})
                print(repr(error), env.errors, flush=True)
                await page.screenshot(path=str(ARGS.saida / (str(len(results)) + '-falha.png')))
            await ctx.close()
            print(name, results[-1]['ok'], flush=True)

        async def courses(e, ctx, page):
            assert 'Sessao is not defined' not in await page.locator('body').inner_text()
            assert await page.locator('#lista').inner_text() != ''
            assert 'Curso simulado' in await page.locator('#lista').inner_text()
            assert 'Sessao is not defined' not in await page.locator('body').inner_text()
            await identity(page, e.name)
            await page.locator('header summary').focus()
            await page.keyboard.press('Enter')
            assert await page.locator('header details').get_attribute('open') is not None
            await page.locator('header summary').click()
            assert await page.locator('header details').get_attribute('open') is None
            # Todos os controles apresentados devem permanecer dentro da viewport.
            assert await page.evaluate('''() => [...document.querySelectorAll('header a,header button,header summary')].every(e=>{
                const r=e.getBoundingClientRect();return !r.width || (r.left>=0 && r.right<=innerWidth+1 && r.top>=0);
            })''')
            assert not await page.evaluate('document.documentElement.scrollWidth > innerWidth')
            assert await page.locator('header .ro-header-titles').evaluate('e=>{const r=e.getBoundingClientRect(),n=document.querySelector(".ro-header-navigation").getBoundingClientRect();return !r.width||r.bottom<=n.top+1||n.bottom<=r.top+1||r.right<=n.left+1||n.right<=r.left+1;}')

        for old in [False, True]:
            for width in SIZES:
                for name in NAMES:
                    await case(f'cursos HTML={"anterior" if old else "atual"} {width}px {name.split()[0]}', Env(old, name), courses, width=width)

        await case('identificação HTML anterior', Env(True), lambda e,c,p: identity(p,e.name))

        async def reload(e, ctx, page):
            await courses(e, ctx, page)
            await page.reload(); await settle(page); await identity(page, e.name)
            assert await page.evaluate('!!localStorage.getItem("me_cache")')
            await page.evaluate('logout()'); await settle(page); await clean(page)
        await case('HTML anterior: refresh e logout', Env(True), reload)

        async def invalid(e, ctx, page):
            await identity(page, e.name)
            e.status = 401
            await page.evaluate('apiGetAuth("/me").catch(()=>{})')
            await clean(page)
        await case('HTML anterior: 401 com cache recente', Env(True), invalid)
        for profile in ['expirada', 'invalida']:
            e = Env(True); e.status = 401
            await case('sessão '+profile, e, lambda e,c,p: clean(p))

        async def switch(e, ctx, page):
            await identity(page, e.name)
            e.name = 'Bruno Costa'
            await page.evaluate('Sessao.definirToken("B");exibirNomeUsuarioLogado()')
            await identity(page, e.name)
            assert 'ANA' not in await page.locator('header').inner_text()
            other = await ctx.new_page()
            other.on('pageerror', lambda err: e.errors.append(str(err)))
            await other.goto(ORIGIN + '/cursos.html'); await settle(other); await identity(other, e.name)
            await page.evaluate('Sessao.encerrar()'); await other.wait_for_timeout(100)
            await clean(other)
        await case('troca de usuário e logout entre abas', Env(True), switch)

        async def normal_login(e, ctx, page):
            await page.wait_for_function('!!window.Sessao')
            await page.locator('#email').fill('aluno@example.invalid');await page.locator('#senha').fill('Simulada1')
            await page.locator('button[type=submit]').click();await settle(page)
            await page.wait_for_url('**/cursos.html');await settle(page)
            await identity(page, e.name)
            assert 'Curso simulado' in await page.locator('#lista').inner_text()
        await case('login com HTML anterior até Meus Cursos', Env(True, token=None), normal_login, 'login.html?next=cursos.html&dummy=')

        async def normal_register(e, ctx, page):
            await page.wait_for_function('!!window.Sessao')
            for field, value in [('nome','Ana Silva'),('email','aluno@example.invalid'),('senha','Simulada1'),('confirmarSenha','Simulada1'),('cpf','52998224725'),('telefone','11999999999')]:
                await page.locator('#'+field).fill(value)
            await page.locator('button[type=submit]').click()
            await page.wait_for_url('**/cursos.html');await settle(page)
            await identity(page, e.name)
        await case('cadastro com HTML anterior até Meus Cursos', Env(True, token=None), normal_register, 'register.html')

        async def delayed(e, ctx, page):
            await page.wait_for_function('!!window.Sessao')
            e.delay_login = asyncio.Event()
            await page.locator('#email').fill('aluno@example.invalid');await page.locator('#senha').fill('Simulada1')
            await page.locator('button[type=submit]').click();await e.login_seen.wait()
            await page.evaluate('Sessao.encerrar()');e.delay_login.set();await settle(page)
            await clean(page)
            assert '/login.html' in page.url
        await case('HTML anterior: login atrasado após logout', Env(True, token=None), delayed, 'login.html')

        async def submit_during_load(e, ctx, page):
            # Recomeça a navegação para interagir antes de a dependência terminar.
            e.session_delay = 1
            await page.reload(wait_until='domcontentloaded')
            await page.locator('#email').fill('aluno@example.invalid')
            await page.locator('#senha').fill('Simulada1')
            await page.locator('button[type=submit]').click()
            assert 'Simulada1' not in page.url
            assert not e.login_seen.is_set()
            await settle(page)
            await page.wait_for_function('!!window.Sessao')
        await case('formulário não navega durante carga da sessão', Env(True, token=None), submit_during_load, 'login.html')

        async def transient(e, ctx, page):
            await identity(page, e.name)
            for status in [403, 500, 503]:
                e.status = status
                await page.evaluate('apiGetAuth("/me").catch(()=>{})')
                assert await page.evaluate('localStorage.getItem("access_token")') == 'A'
                await identity(page, e.name)
        await case('HTML anterior: 403/5xx preservam sessão', Env(True), transient)

        async def admin(e, ctx, page):
            assert await page.evaluate('requireAdmin()')
            await identity(page, e.name)
            assert await page.evaluate('typeof Sessao === "object" && Sessao === window.Sessao && Sessao === globalThis.Sessao')
        await case('admin com HTML anterior', Env(True, admin=True), admin, 'admin/index.html')
        e = Env(True); e.session_delay = .3
        async def single(e, ctx, page):
            await courses(e, ctx, page)
            assert await page.locator('script[src$="/js/sessao.js"]').count() == 1
            assert await page.locator('script[src$="/js/cabecalho.js"]').count() == 1
        await case('carregamento lento compartilha uma única dependência', e, single)
        for file in ['curso.html', 'disciplinas.html', 'assuntos.html', 'dashboard.html']:
            await case('navegação HTML anterior: '+file, Env(file != 'dashboard.html'), lambda e,c,p: identity(p,e.name), file)
        async def static_lesson(e, ctx, page):
            assert await page.locator('header h1').count() == 1
            assert not await page.locator('.ro-identity').count()
        await case('aula estática mantém apresentação sem identificação', Env(), static_lesson, 'aula.html')
        await browser.close()
    (ARGS.saida / 'resultados.json').write_text(json.dumps(results, ensure_ascii=False, indent=2))
    failed = [r for r in results if not r['ok']]
    print(json.dumps({'total': len(results), 'falhas': len(failed), 'saida': str(ARGS.saida)}))
    raise SystemExit(bool(failed))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--filtro', help='Expressão regular dos cenários a executar')
    parser.add_argument('--codigo', help='Ref Git do JS a testar; padrão: arquivos desta worktree')
    parser.add_argument('--saida', type=Path, default=Path('/tmp/resumao-carregamento'))
    ARGS = parser.parse_args()
    asyncio.run(main())
