"""Laboratório Fase 2: PostgreSQL local persistente + ponte TestClient.

Não importa app.database, não lê .env e não herda credenciais/DSN de implantação.
Storage fica bloqueado até início explícito com --liberar-storage, após autorização.
"""
import argparse
import base64
import getpass
import json
import os
from pathlib import Path
import secrets
import socket
import stat
import subprocess
import sys
import time
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
ESTADO = Path('/tmp/resumao-fase2-homologacao')
CONTAINER = 'resumao-fase2-homologacao-pg'
VOLUME = CONTAINER + '-dados'
BANCO = 'resumao_imagens_homologacao'
LABEL = 'resumao.fase2.homologacao'
PYTHON_REUSADO = Path('/workspaces/resumao-editor-teoria-dev/.local/ckeditor-seguranca-venv/bin/python')


def ambiente_seguro():
    # Lista positiva: jamais importar .env nem propagar chaves de outros serviços.
    preservar = {'PATH', 'LANG', 'LC_ALL', 'TERM', 'HOME', 'USER', 'TMPDIR', 'PYTHONPATH',
                 'CKEDITOR_TEST_DIST', 'DOCKER_HOST', 'DOCKER_CONTEXT', 'DOCKER_CONFIG'}
    ambiente = {k:v for k,v in os.environ.items() if k in preservar}
    ambiente.update(AMBIENTE_TESTE='1', IMAGENS_MANUTENCAO_ATIVA='false', EMAILS_PAGAMENTOS_ATIVOS='false',
                    IMAGENS_HOSTS_PERMITIDOS='', PYTHONDONTWRITEBYTECODE='1')
    return ambiente


def pasta_privada():
    if ESTADO.is_symlink():
        raise RuntimeError('Diretório de estado inseguro.')
    ESTADO.mkdir(mode=0o700, exist_ok=True)
    if ESTADO.stat().st_uid != os.getuid():
        raise RuntimeError('O estado deve pertencer ao usuário local.')
    ESTADO.chmod(0o700)


def escrever_privado(nome, dados):
    pasta_privada()
    destino = ESTADO / nome
    temporario = ESTADO / (nome + '.tmp-' + secrets.token_hex(8))
    fd = os.open(temporario, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as out:
        out.write(dados)
    os.replace(temporario, destino)


def ler_privado(nome):
    pasta_privada()
    caminho = ESTADO / nome
    s = caminho.lstat()
    if not stat.S_ISREG(s.st_mode) or s.st_uid != os.getuid() or s.st_mode & 0o077:
        raise RuntimeError('Arquivo de configuração deve ser privado (0600).')
    return json.loads(caminho.read_text())


def docker(*args, verificar=True):
    # Somente contexto Docker local por socket; não usar daemon remoto herdado.
    ambiente = {**os.environ, 'DOCKER_HOST':'unix:///var/run/docker.sock'}
    ambiente.pop('DOCKER_CONTEXT', None)
    return subprocess.run(['docker', *args], check=verificar, capture_output=True,
                          text=True, timeout=30, env=ambiente)


def conferir_container():
    r = docker('inspect', '--format', '{{json .Config.Labels}}|{{.HostConfig.NetworkMode}}|{{json .Mounts}}', CONTAINER)
    labels, rede, mounts = r.stdout.strip().split('|')
    if json.loads(labels).get(LABEL) != '1' or rede != 'none':
        raise RuntimeError('Contêiner não corresponde ao laboratório isolado.')
    mounts = json.loads(mounts)
    if not any(m.get('Type')=='volume' and m.get('Name')==VOLUME for m in mounts):
        raise RuntimeError('Volume do laboratório não corresponde ao esperado.')
    if not any(m.get('Type')=='bind' and m.get('Source')==str(ESTADO/'pgsocket')
               and m.get('Destination')=='/var/run/postgresql' for m in mounts):
        raise RuntimeError('Socket do laboratório não corresponde ao esperado.')


def motor_local(runtime):
    conferir_container()
    caminho = ESTADO/'pgsocket'/'.s.PGSQL.5432'
    if not stat.S_ISSOCK(caminho.stat().st_mode):
        raise RuntimeError('Socket PostgreSQL local ausente.')
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import URL
    engine = create_engine(URL.create('postgresql+psycopg', username='postgres',
        password=runtime['pg_password'], database=BANCO, query={'host':str(ESTADO/'pgsocket')}),
        connect_args={'connect_timeout':3,'prepare_threshold':None},pool_size=3,max_overflow=0)
    with engine.connect() as db:
        if db.execute(text('SELECT current_database()')).scalar() != BANCO:
            raise RuntimeError('Banco inesperado.')
    return engine


def conferir_identidade(engine, runtime):
    from sqlalchemy import text
    with engine.connect() as db:
        if db.execute(text('SELECT identidade FROM homologacao_imagens_controle WHERE id=1')).scalar() != runtime['identidade']:
            raise RuntimeError('Identidade do banco diverge do laboratório; não reinicializar automaticamente.')


def preparar():
    pasta_privada()
    existe = docker('container', 'inspect', CONTAINER, verificar=False).returncode == 0
    if not (ESTADO/'runtime.json').exists():
        volume_existe = docker('volume', 'inspect', VOLUME, verificar=False).returncode == 0
        if existe or volume_existe:
            raise RuntimeError('Estado local ausente com contêiner/volume já existente. Preservado para investigação.')
        runtime = {'identidade':secrets.token_hex(24),'pg_password':secrets.token_urlsafe(32),
                   'jwt_secret':secrets.token_urlsafe(48)}
        escrever_privado('runtime.json', json.dumps(runtime))
    runtime = ler_privado('runtime.json')
    if not existe:
        (ESTADO/'pgsocket').mkdir(mode=0o777, exist_ok=True)
        (ESTADO/'pgsocket').chmod(0o777)
        escrever_privado('postgres.env','POSTGRES_PASSWORD='+runtime['pg_password']+'\nPOSTGRES_DB='+BANCO+'\nPOSTGRES_INITDB_ARGS=--auth-local=scram-sha-256\n')
        docker('volume','create','--label',LABEL+'=1',VOLUME)
        docker('run','--detach','--network','none','--name',CONTAINER,'--label',LABEL+'=1',
            '--env-file',str(ESTADO/'postgres.env'),'--mount',f'type=volume,source={VOLUME},target=/var/lib/postgresql/data',
            '--mount',f'type=bind,source={ESTADO}/pgsocket,target=/var/run/postgresql','postgres:17.6')
    else:
        conferir_container()
        docker('start',CONTAINER)
    for _ in range(60):
        if docker('exec',CONTAINER,'pg_isready','-h','127.0.0.1','-U','postgres',verificar=False).returncode==0:
            break
        time.sleep(.25)
    engine = motor_local(runtime)
    from sqlalchemy import inspect, text
    from sqlalchemy.orm import sessionmaker
    from app import models as m
    if inspect(engine).has_table('homologacao_imagens_controle'):
        conferir_identidade(engine,runtime)
    else:
        # Reaproveita a seleção de modelos dos testes, fechando dependências FK.
        from test_aulas_admin import MODELOS
        tabelas = {modelo.__table__ for modelo in MODELOS}
        while True:
            novas = {fk.column.table for t in tabelas for fk in t.foreign_keys}
            if novas.issubset(tabelas):break
            tabelas |= novas
        m.Base.metadata.create_all(engine, tables=list(tabelas))
        # Exclusivamente no PostgreSQL local acima, sem SQL no Supabase.
        with engine.connect() as db:
            db.exec_driver_sql((ROOT/'backend/migrations/024_imagens_teoria.sql').read_text())
            db.commit()
        with sessionmaker(engine)() as db:
            from datetime import datetime, timedelta
            if db.query(m.Usuario).count():
                raise RuntimeError('Banco sem marcador já contém usuários; não sobrescrito.')
            db.add_all([m.Usuario(id=1,nome='Admin fictício',email='admin@homologacao.invalid',senha_hash='login-desabilitado',
                cpf='homologacao-admin',telefone='0',is_admin=True,tipo_admin='admin_geral'),
                m.Usuario(id=2,nome='Aluno fictício',email='aluno@homologacao.invalid',senha_hash='login-desabilitado',
                cpf='homologacao-aluno',telefone='0',is_admin=False)])
            db.add(m.Curso(id=1,nome='Curso fictício Fase 2'));db.flush()
            db.add(m.CursoDisciplinaPropria(id=1,curso_id=1,nome='Disciplina fictícia'));db.flush()
            db.add(m.CursoAssuntoProprio(id=1,curso_disciplina_propria_id=1,nome='Assunto fictício'));db.flush()
            db.add(m.Pasta(id=1,curso_assunto_proprio_id=1,tipo='TEORIA',nome='Teoria'));db.flush()
            db.add(m.Aula(id=1,pasta_id=1,titulo='Homologação de imagens'))
            db.add(m.ContratacaoCurso(id=1,usuario_id=2,curso_id=1,origem='ADMIN',
                data_inicio=datetime.utcnow()-timedelta(days=1),data_fim=datetime.utcnow()+timedelta(days=365)))
            db.commit()
        with engine.begin() as db:
            db.execute(text('CREATE TABLE homologacao_imagens_controle(id INTEGER PRIMARY KEY, identidade TEXT NOT NULL)'))
            db.execute(text('INSERT INTO homologacao_imagens_controle VALUES (1,:id)'),{'id':runtime['identidade']})
    engine.dispose()
    print('PostgreSQL local preparado: sem rede TCP/portas publicadas; volume persistente e dados fictícios.')
    print('Storage BLOQUEADO. Manutenção automática false. Nenhum acesso ao Supabase realizado.')


def configurar():
    pasta_privada()
    if not sys.stdin.isatty():
        raise RuntimeError('Configure as credenciais apenas em terminal interativo privado.')
    url = getpass.getpass('URL HTTPS do projeto Supabase (entrada oculta): ').strip().rstrip('/')
    partes = urlsplit(url)
    if partes.scheme!='https' or not partes.hostname or partes.netloc!=partes.hostname or partes.path or partes.query or partes.fragment:
        raise RuntimeError('URL inválida.')
    chave = getpass.getpass('Chave secreta do projeto para homologação (entrada oculta): ').strip()
    os.environ.update(SUPABASE_URL=url,SUPABASE_SECRET_KEY=chave,SUPABASE_IMAGENS_BUCKET='teoria-imagens')
    from app.imagens_storage import SupabaseImagens
    SupabaseImagens()  # Validação local de formato, SEM requisição HTTP.
    escrever_privado('supabase.json',json.dumps({'url':url,'key':chave,'bucket':'teoria-imagens'}))
    print('Configuração salva fora do Git, em arquivo 0600. Storage continua bloqueado; nenhum acesso remoto.')


def bridge(liberar):
    runtime=ler_privado('runtime.json');engine=motor_local(runtime);conferir_identidade(engine,runtime)
    os.environ['SECRET_KEY']=runtime['jwt_secret']
    origem=''
    if liberar:
        config=ler_privado('supabase.json')
        if config['bucket']!='teoria-imagens':raise RuntimeError('Bucket inesperado.')
        os.environ.update(SUPABASE_URL=config['url'],SUPABASE_SECRET_KEY=config['key'],SUPABASE_IMAGENS_BUCKET=config['bucket'])
        origem=config['url']
    from fastapi import HTTPException
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker
    from app.imagens_storage import obter_storage_imagens, SupabaseImagens
    from test_questoes_pratica_patch import carregar_main_isolado
    factory=sessionmaker(engine,autoflush=False)
    def bloqueado():
        raise HTTPException(503,'Storage bloqueado nesta preparação; aguarde autorização para testes reais.')
    try:
        with carregar_main_isolado(factory,engine) as main:
            main.app.dependency_overrides[obter_storage_imagens]=(lambda:SupabaseImagens()) if liberar else bloqueado
            # Sem lifespan: não iniciar workers financeiros nem manutenção. JWT
            # e permissões reais são preservados; nenhuma autenticação é mockada.
            client=TestClient(main.app,raise_server_exceptions=False)
            from app.auth import criar_token
            print(json.dumps({'ready':True,'storageLiberado':liberar,'storageOrigin':origem,
                'tokens':{'admin':criar_token({'sub':'1'}),'aluno':criar_token({'sub':'2'})}}),flush=True)
            for linha in sys.stdin:
                try:
                    req=json.loads(linha)
                    r=client.request(req['method'],req['path'],content=base64.b64decode(req.get('base64','')),
                                     headers=req.get('headers',{}))
                    print(json.dumps({'status':r.status_code,'body':r.json()}),flush=True)
                except Exception:
                    print(json.dumps({'status':500,'body':{'detail':'Falha local no laboratório; nenhum segredo foi registrado.'}}),flush=True)
            client.close()
    finally:engine.dispose()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('acao',choices=['preparar','configurar','iniciar','bridge'])
    parser.add_argument('--liberar-storage',action='store_true',help='Somente após autorização para testes reais, permite operações no bucket.')
    args=parser.parse_args()
    # Reaproveitar as dependências locais já instaladas, sem instalar pacotes.
    if PYTHON_REUSADO.exists() and Path(sys.prefix)!=PYTHON_REUSADO.parent.parent:
        os.execv(str(PYTHON_REUSADO),[str(PYTHON_REUSADO),str(Path(__file__).resolve()),*sys.argv[1:]])
    ambiente=ambiente_seguro();os.environ.clear();os.environ.update(ambiente)
    sys.dont_write_bytecode=True
    os.environ['SECRET_KEY']=secrets.token_urlsafe(48)
    if Path('/tmp/resumao-fase2-deps').exists():sys.path.insert(0,'/tmp/resumao-fase2-deps')
    if args.acao=='preparar':preparar()
    elif args.acao=='configurar':configurar()
    elif args.acao=='bridge':bridge(args.liberar_storage)
    else:
        ambiente=dict(os.environ, FASE2_PYTHON=sys.executable)
        os.execvpe('node',['node',str(ROOT/'site-html/homologacao-imagens.cjs'),
                         *(['--liberar-storage'] if args.liberar_storage else [])],ambiente)


if __name__=='__main__':
    try:main()
    except Exception:
        print('Preparação interrompida. Confira os pré-requisitos locais e os arquivos privados; nenhum detalhe sensível foi registrado.',file=sys.stderr)
        sys.exit(1)
