"""Advisory locks reais em PostgreSQL descartável, sem portas/rede/migration."""
import os
import subprocess
import tempfile
import time
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker
from app.imagens_manutencao import travar_objeto, exclusao_mutua


@pytest.mark.skipif(os.getenv('IMAGENS_TESTAR_LOCKS_PG')!='1',reason='Requer Docker e postgres:17.6 local')
def test_lock_upload_reconciliacao_e_multiplos_workers():
    nome='resumao-imagens-locks-'+uuid4().hex[:10]
    def comando(*args):
        return subprocess.run(args,capture_output=True,text=True,check=True,timeout=20)
    with tempfile.TemporaryDirectory(prefix='resumao-imagens-locks-') as socket:
        os.chmod(socket,0o777)
        comando('docker','run','--detach','--rm','--network','none','--name',nome,
                '--mount',f'type=bind,source={socket},target=/var/run/postgresql',
                '-e','POSTGRES_PASSWORD=senha-sintetica-local','-e','POSTGRES_DB=imagens_locks_test','postgres:17.6')
        engine=None
        try:
            for _ in range(60):
                r=subprocess.run(['docker','exec',nome,'pg_isready','-h','127.0.0.1','-U','postgres'],capture_output=True,timeout=5)
                if r.returncode==0:break
                time.sleep(.25)
            engine=create_engine(URL.create('postgresql+psycopg',username='postgres',password='senha-sintetica-local',
                database='imagens_locks_test',query={'host':socket}),connect_args={'connect_timeout':3})
            factory=sessionmaker(engine)
            chave=str(uuid4())+'.png'
            with factory() as upload,factory() as reconciliador:
                assert travar_objeto(upload,chave)
                assert not travar_objeto(reconciliador,chave,esperar=False)
                reconciliador.rollback();upload.commit()
                assert travar_objeto(reconciliador,chave,esperar=False)
                reconciliador.rollback()
                assert travar_objeto(upload,chave,esperar=False)
            with exclusao_mutua(engine,'bucket-exclusivo-teste') as primeiro:
                assert primeiro
                with factory() as db:db.commit()
                with exclusao_mutua(engine,'bucket-exclusivo-teste') as segundo:assert not segundo
            with exclusao_mutua(engine,'bucket-exclusivo-teste') as novo:assert novo
        finally:
            if engine:engine.dispose()
            # O entrypoint PostgreSQL muda o dono do mount; devolver ao usuário
            # do teste antes que TemporaryDirectory remova seu próprio diretório.
            comando('docker','exec','-u','0',nome,'chown',f'{os.getuid()}:{os.getgid()}','/var/run/postgresql')
            comando('docker','exec','-u','0',nome,'chmod','0777','/var/run/postgresql')
            comando('docker','stop','--time','2',nome)
