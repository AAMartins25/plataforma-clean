"""Importação de uma árvore nova. A sessão pertence ao chamador; nenhum commit intermediário."""
import copy
import hashlib
import json
import re
from fastapi import HTTPException
from sqlalchemy import func, text
from pydantic import ValidationError
from app import models as m
from app.aulas import validar_conclusao
from app.descricao_publica import preparar_descricao
from app.teoria_html import preparar_conteudo
from app.importacao_esquemas import ImportacaoCursoV1

LIMITE_BYTES = 128 * 1024 * 1024
# Impede imagens convencionais e HTML, inclusive imagens de referência Markdown.
IMAGEM = re.compile(r'!\s*\[|<\s*img\b|&(?:lt|#0*60|#x0*3c);\s*img\b', re.I)


def _validar_par(original, convertido, caminho=''):
    if isinstance(original, dict) and isinstance(convertido, dict):
        if original.keys() != convertido.keys():
            raise HTTPException(422, f'{caminho}: estrutura convertida divergente')
        for k in original:
            _validar_par(original[k], convertido[k], f'{caminho}.{k}' if caminho else k)
    elif isinstance(original, list) and isinstance(convertido, list):
        if len(original) != len(convertido):
            raise HTTPException(422, f'{caminho}: estrutura convertida divergente')
        for i, (a,b) in enumerate(zip(original, convertido)):
            _validar_par(a,b,f'{caminho}[{i}]')
    elif isinstance(original, str) and isinstance(convertido, str) and (caminho.endswith('_markdown') or '.alternativas.' in caminho):
        if IMAGEM.search(original) or IMAGEM.search(convertido):
            raise HTTPException(422, f'{caminho}: imagens não são suportadas nesta versão')
    elif original != convertido or type(original) is not type(convertido):
        raise HTTPException(422, f'{caminho}: conteúdo convertido divergente')


def preparar(original, convertido):
    _validar_par(original, convertido)
    try:
        fonte = ImportacaoCursoV1.model_validate(original)
    except ValidationError as exc:
        erros = [{'local': '.'.join(map(str, e['loc'])), 'mensagem': e['msg']} for e in exc.errors(include_url=False, include_context=False, include_input=False)]
        raise HTTPException(422, erros) from exc
    if sum(len(d.assuntos) for d in fonte.disciplinas) > 10000:
        raise HTTPException(422, 'O arquivo excede 10.000 assuntos.')
    # Preparar e validar todo o conteúdo antes de iniciar qualquer gravação.
    h = copy.deepcopy(convertido)
    for campo in ('nome', 'banca', 'cargo', 'orgao', 'ano', 'uf'):
        h['curso'][campo] = getattr(fonte.curso, campo)
    def limpar(valor, caminho, descricao=False):
        try:
            from app.registros_html import texto_visivel
            if descricao:
                resultado = preparar_descricao({'descricao_publica': valor, 'descricao_publica_formato':'html_v1'}, None)
                if not texto_visivel(resultado, 'html_v1').strip() and '<hr>' not in resultado:
                    raise HTTPException(422, 'A descrição ficou vazia após sanitização.')
                return resultado
            resultado = preparar_conteudo(valor, 'html_v1')
            if not texto_visivel(resultado, 'html_v1').strip():
                raise HTTPException(422, 'O conteúdo ficou vazio após sanitização.')
            return resultado
        except HTTPException as exc:
            raise HTTPException(422, [{'local': caminho, 'mensagem': str(exc.detail)}]) from exc
    h['curso']['descricao_publica_markdown'] = limpar(h['curso']['descricao_publica_markdown'], 'curso.descricao_publica_markdown', True)
    for di, d in enumerate(h['disciplinas']):
        for ai, a in enumerate(d['assuntos']):
            caminho = f'disciplinas[{di}].assuntos[{ai}]'
            for ri, resumo in enumerate(a['resumos']):
                resumo['texto_markdown'] = limpar(resumo['texto_markdown'], f'{caminho}.resumos[{ri}].texto_markdown')
            for bi, bateria in enumerate(a['baterias']):
                for qi, q in enumerate(bateria['questoes']):
                    prefixo = f'{caminho}.baterias[{bi}].questoes[{qi}]'
                    for campo in ('enunciado_markdown', 'comentario_markdown'):
                        q[campo] = limpar(q[campo], f'{prefixo}.{campo}')
                    q['alternativas'] = {k: limpar(v, f'{prefixo}.alternativas.{k}') for k,v in q['alternativas'].items()}
    return h


def importar(db, usuario_id, chave, original, convertido):
    if not isinstance(chave, str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,64}', chave):
        raise HTTPException(422, 'Chave de idempotência inválida.')
    dados = preparar(original, convertido)
    digest = hashlib.sha256(json.dumps([original, convertido], sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
    if db.bind.dialect.name == 'postgresql':
        db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:chave, 0))'), {'chave':'importacao:' + chave})
    anterior = db.get(m.ImportacaoCurso, chave)
    if anterior:
        if anterior.usuario_id != usuario_id or anterior.hash_requisicao != digest:
            raise HTTPException(409, 'Chave de importação já usada para outra solicitação.')
        return {'curso_id': anterior.curso_id, 'repetida': True}
    c = dados['curso']
    nome = c['nome'].strip()
    if db.bind.dialect.name == 'postgresql':
        db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:nome, 0))'), {'nome':'curso_nome:' + nome.lower()})
    if db.query(m.Curso.id).filter(func.lower(m.Curso.nome) == nome.lower()).first():
        raise HTTPException(409, 'Já existe um curso com esse nome.')
    curso = m.Curso(nome=nome, banca=c['banca'], cargo=c['cargo'], orgao=c['orgao'], ano=c['ano'], uf=c['uf'], produtor_id=usuario_id, ativo=True, publicado=False, precos_provisorios=True, demonstracao_por_ordem=True, descricao_publica=c['descricao_publica_markdown'])
    db.add(curso); db.flush()
    for meses in (4,8,12):
        db.add(m.TempoAcessoCurso(curso_id=curso.id, meses=meses, valor_cents=meses,
                                  valor_provisorio_original_cents=meses, ativo=True))
    for di, disciplina in enumerate(dados['disciplinas'], 1):
        disc = m.CursoDisciplinaPropria(curso_id=curso.id, nome=disciplina['nome'].strip(), ordem=di, ativo=True,
                                         disponivel_demonstracao=di <= 2)
        db.add(disc); db.flush()
        for ai, assunto in enumerate(disciplina['assuntos'], 1):
            ass = m.CursoAssuntoProprio(curso_disciplina_propria_id=disc.id, nome=assunto['nome'].strip(), ordem=ai, ativo=True)
            db.add(ass); db.flush()
            pasta = m.Pasta(curso_assunto_proprio_id=ass.id, tipo='TEORIA', nome='Aulas')
            db.add(pasta); db.flush()
            aula = m.Aula(pasta_id=pasta.id, titulo=assunto['aula_titulo'].strip(), ordem=1, ativo=True)
            db.add(aula); db.flush()
            for ri, resumo in enumerate(assunto['resumos'], 1):
                db.add(m.Material(aula_id=aula.id, tipo='TEXTO', titulo=resumo['titulo'].strip(), conteudo=resumo['texto_markdown'], conteudo_formato='html_v1', ordem=ri, ativo=True))
            for bi, bateria in enumerate(assunto['baterias'], 1):
                bat = m.Bateria(aula_id=aula.id, titulo=bateria['titulo'].strip(), ordem=bi, status='EM_ANDAMENTO', ativo=True)
                db.add(bat); db.flush()
                for qi, q in enumerate(bateria['questoes'], 1):
                    questao = m.Questao(bateria_id=bat.id, enunciado=q['enunciado_markdown'], enunciado_formato='html_v1', comentario=q['comentario_markdown'], comentario_formato='html_v1', tipo=bateria['tipo'], tipo_questao=q['tipo'], quantidade_alternativas={'MULTIPLA_4':4,'MULTIPLA_5':5,'CERTO_ERRADO':2}[q['tipo']], gabarito=q['gabarito'], ordem=qi, ativo=True)
                    db.add(questao); db.flush()
                    for letra, valor in q['alternativas'].items():
                        db.add(m.Alternativa(questao_id=questao.id, letra=letra, texto=valor, texto_formato='html_v1'))
                db.flush(); validar_conclusao(db, bat); bat.status='CONCLUIDA'
    db.add(m.ImportacaoCurso(chave=chave, hash_requisicao=digest, usuario_id=usuario_id, curso_id=curso.id))
    db.commit()
    return {'curso_id':curso.id, 'repetida':False}
