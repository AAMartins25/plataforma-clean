"""Prévia exclusiva de testes: SQLite e arquivos em /tmp; nunca carrega app.database real.
Executar na raiz da worktree: python backend/preview_questoes_editor.py
"""
import os
from pathlib import Path
import secrets
import sys
from datetime import datetime, timedelta

# Caminhos exclusivos da prévia podem ser fornecidos sem herdar credenciais.
import argparse
opcoes = argparse.ArgumentParser(description=__doc__)
opcoes.add_argument('--dados', default='/tmp/resumao-questoes-editor-visual')
opcoes.add_argument('--ckeditor-dist', default='/tmp/resumao-questoes-browser/node_modules/ckeditor5/dist/browser')
opcoes.add_argument('--porta', type=int, default=8769)
preview = opcoes.parse_args()

# Credenciais/DSNs herdados não fazem parte desta aplicação descartável.
os.environ.clear()
os.environ.update(AMBIENTE_TESTE='1', SECRET_KEY=secrets.token_hex(32),
                  CKEDITOR_LICENSE_KEY='GPL', QUESTOES_PRATICA_SESSION_SECRET=secrets.token_hex(32))
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from fastapi import Request, HTTPException
from fastapi.responses import HTMLResponse, Response, FileResponse
import uvicorn
from app import models as m
from test_questoes_pratica_patch import carregar_main_isolado
from test_imagens_teoria import StorageMemoria, png
from app.imagens_storage import obter_storage_imagens

ROOT = Path(__file__).resolve().parents[1]
DADOS = Path(preview.dados)
DADOS.mkdir(exist_ok=True)
engine = create_engine('sqlite:///' + str(DADOS / 'preview.sqlite'), connect_args={'check_same_thread': False})
@event.listens_for(engine, 'connect')
def configurar(conexao, _):
    conexao.create_function('BTRIM', 1, lambda v: v.strip() if v is not None else None, deterministic=True)
    conexao.execute('PRAGMA foreign_keys=ON')
factory = sessionmaker(bind=engine, autoflush=False)
# Exclui apenas evidências jurídicas PostgreSQL, sem relação com a prévia.
from test_aulas_admin import MODELOS
extras=[m.ReformulacaoConversaOperacao,m.Vendedor,m.AcessoCurso,m.TempoAcessoCurso,m.QuestaoPraticaAssunto,m.QuestaoPraticaAlternativa,
        m.QuestaoPraticaMarcacaoAluno,m.QuestaoPraticaRotatividadeAluno]
m.Base.metadata.create_all(engine, tables=[modelo.__table__ for modelo in MODELOS + extras])

class StoragePreview(StorageMemoria):
    def __init__(self):
        super().__init__()
        self.pasta = DADOS / 'imagens'
        self.pasta.mkdir(exist_ok=True)
        for arquivo in self.pasta.iterdir():
            mime = {'.png': 'image/png', '.jpg': 'image/jpeg', '.webp': 'image/webp'}.get(arquivo.suffix)
            if mime:self.objetos[arquivo.name] = (arquivo.read_bytes(), mime)

    def enviar(self, chave, dados, mime):
        super().enviar(chave, dados, mime)
        (self.pasta / chave).write_bytes(dados)

    def excluir(self, chave):
        super().excluir(chave)
        (self.pasta / chave).unlink(missing_ok=True)

storage = StoragePreview()
with carregar_main_isolado(factory, engine) as main:
    if not (DADOS / 'semente-pronta').exists():
        with factory() as db:
            for id, admin in [(1, True), (2, False)]:
                db.add(m.Usuario(id=id, nome='ADM isolado' if admin else 'Aluno isolado', email=f'preview{id}@example.org',
                    senha_hash='sem-login-real', cpf=str(id), telefone='0', is_admin=admin, tipo_admin='admin_geral' if admin else None, ativo=True))
            db.add(m.Curso(id=1,nome='Curso de teste — Editor de Questões', publicado=False,ativo=True));db.flush()
            db.add(m.CursoDisciplinaPropria(id=1,curso_id=1,nome='Disciplina de teste',disponivel_demonstracao=True));db.flush()
            db.add(m.CursoAssuntoProprio(id=1,curso_disciplina_propria_id=1,nome='Assunto de teste'));db.flush()
            db.add(m.CursoAssuntoProprio(id=2,curso_disciplina_propria_id=1,nome='Assunto livre para criar questões',ordem=2));db.flush()
            db.add(m.Pasta(id=1,curso_assunto_proprio_id=1,tipo='TEORIA',nome='Teoria'));db.flush()
            db.add(m.Pasta(id=2,curso_assunto_proprio_id=2,tipo='TEORIA',nome='Teoria'));db.flush()
            db.add(m.Aula(id=1,pasta_id=1,titulo='Aula de teste'));db.flush()
            db.add(m.Aula(id=2,pasta_id=2,titulo='Aula livre para criar questões',ordem=2));db.flush()
            db.add(m.Bateria(id=1,aula_id=1,titulo='Bateria formatada',status='EM_ANDAMENTO',ordem=1));db.flush()
            db.add(m.ContratacaoCurso(id=1,usuario_id=2,curso_id=1,origem='ADMIN',data_inicio=datetime.utcnow()-timedelta(days=1),data_fim=datetime.utcnow()+timedelta(days=30)))
            db.add(m.Material(aula_id=1,titulo='Referência do editor',tipo='TEXTO',conteudo='<h2>Teoria de teste</h2><p><strong>Mesmo editor</strong> das questões.</p>',conteudo_formato='html_v1'))
            from app.imagens_arquivos import validar_imagem
            figura = validar_imagem(png('royalblue'))
            imagem_id = '22222222-2222-4222-8222-222222222222'
            chave = imagem_id + '.' + figura.extensao
            storage.enviar(chave, figura.dados, figura.mime)
            db.add(m.ImagemTeoria(id=imagem_id,chave=chave,autor_id=1,mime=figura.mime,tamanho=len(figura.dados),largura=figura.largura,altura=figura.altura,sha256=figura.sha256))
            db.commit()
            for i in range(1,11):
                tipo='MULTIPLA_5' if i==1 else ('MULTIPLA_4' if i==2 else 'CERTO_ERRADO')
                legado=i==3
                enunciado='Legado <b>literal</b> & x < y\nLinha preservada' if legado else f'<h2>Questão {i}</h2><p><strong>Enunciado formatado</strong> com <u>sublinhado</u> e <i>itálico</i>.</p><p>Fórmula: <span class="ro-math-inline">x^2 + y^2</span></p><figure class="table"><table><tr><th>Item</th><th>Detalhe</th><th>Conclusão</th></tr><tr><td>A</td><td>Texto de teste</td><td>Preservado</td></tr></table></figure>'
                if i == 1:enunciado += '<figure class="image"><img src="/midias/imagens/' + imagem_id + '" alt="Figura sintética de teste"><figcaption>Imagem própria de teste</figcaption></figure>'
                comentario='Comentário antigo\nSegunda linha' if legado else '<p><strong>Comentário formatado</strong></p><ul><li>Explicação</li><li>Fundamento</li></ul>'
                payload=main.QuestaoCreate(bateria_id=1,tipo='CERTO_ERRADO' if tipo=='CERTO_ERRADO' else 'MULTIPLA',tipo_questao=tipo,
                    gabarito='E' if tipo=='CERTO_ERRADO' else 'A',enunciado=enunciado,comentario=comentario,
                    enunciado_formato='texto_puro' if legado else 'html_v1',comentario_formato='texto_puro' if legado else 'html_v1',
                    alternativas=[] if tipo=='CERTO_ERRADO' else [{'letra':l,'texto':f'<p><strong>Alternativa {l}</strong></p>','texto_formato':'html_v1'} for l in ('ABCDE' if tipo=='MULTIPLA_5' else 'ABCD')])
                main.criar_questao(payload,db,db.get(m.Usuario,1))
            main.concluir_bateria(1,db,db.get(m.Usuario,1))
            db.get(m.Bateria,1).status='CONCLUIDA'
            db.add(m.RevisaoAluno(id=1,usuario_id=2,pasta_id=1,aula_id=1,contratacao_id=1,etapa=1,status='PENDENTE',data_prevista=datetime.utcnow()-timedelta(days=1)))
            db.commit()
        (DADOS / 'semente-pronta').write_text('Dados sintéticos exclusivos desta prévia.\n')

    with factory() as db:
        for id in (1,2):db.get(m.Usuario,id).email=f'preview{id}@example.org'
        db.commit()

    def usuario_preview(request: Request):
        token=request.headers.get('authorization','').removeprefix('Bearer ')
        if token not in {'isolado-admin','isolado-aluno'}:raise HTTPException(401,'Entre pela página /__preview.')
        with factory() as db:
            return db.get(m.Usuario,1 if token=='isolado-admin' else 2)
    main.app.dependency_overrides[main.get_usuario_atual]=usuario_preview
    main.app.dependency_overrides[obter_storage_imagens]=lambda:storage

    @main.app.get('/__imagens/{chave}')
    def imagem(chave: str):
        if chave not in storage.objetos:raise HTTPException(404)
        dados,mime=storage.objetos[chave];return Response(dados,media_type=mime)

    @main.app.get('/__preview', response_class=HTMLResponse)
    def entrada():
        return '''<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Teste isolado — Questões</title><style>body{font:18px system-ui;max-width:800px;margin:40px auto;padding:20px}a{display:block;margin:20px 0}</style><h1>Editor de Questões — ambiente isolado</h1><p>Dados sintéticos em SQLite. Nenhum banco ou serviço de produção é utilizado.</p><a href="/__preview/entrar?perfil=admin">Abrir Painel ADM</a><a href="/__preview/entrar?perfil=aluno">Resolver bateria como aluno</a><a href="/__preview/entrar?perfil=revisao">Abrir revisão programada</a><p>No ADM: selecione o curso de teste → usar curso → disciplina → assunto → aula → Questões → abrir bateria → editar questão. As questões 1 e 2 são de múltipla escolha; a 3 contém texto legado. Para criar uma bateria sem histórico, use o “Assunto livre para criar questões”.</p></html>'''

    @main.app.get('/__preview/entrar',response_class=HTMLResponse)
    def entrar(perfil: str='admin'):
        destino='admin/criar-curso-completo.html' if perfil=='admin' else 'sprint.html?bateria_id=1&contratacao_id=1&curso_id=1&modo=resolver' + ('&revisao_id=1' if perfil=='revisao' else '')
        token='isolado-admin' if perfil=='admin' else 'isolado-aluno'
        import json
        return '<script>localStorage.clear();localStorage.setItem("access_token",'+json.dumps(token)+');location.href='+json.dumps('/'+destino)+'</script>'

    @main.app.get('/__ckeditor/{asset}')
    def ckeditor(asset: str):
        pasta=Path(preview.ckeditor_dist)
        if asset not in {'ckeditor5.umd.js','ckeditor5.css'}:raise HTTPException(404)
        arquivo=pasta/asset
        if not arquivo.exists():arquivo=pasta.parent/asset
        return FileResponse(arquivo)

    @main.app.get('/{asset_path:path}')
    def static(asset_path: str,request: Request):
        arquivo=(ROOT/'site-html'/asset_path).resolve()
        if not arquivo.is_relative_to(ROOT/'site-html') or not arquivo.is_file():raise HTTPException(404)
        if arquivo.suffix in {'.html','.js'}:
            texto=arquivo.read_text().replace('https://plataforma-quality-backend.onrender.com',str(request.base_url).rstrip('/')).replace('https://cdn.ckeditor.com/ckeditor5/${VERSAO}','/__ckeditor')
            return Response(texto,media_type='text/javascript' if arquivo.suffix=='.js' else 'text/html')
        return FileResponse(arquivo)

    if __name__=='__main__':uvicorn.run(main.app,host='127.0.0.1',port=preview.porta)
