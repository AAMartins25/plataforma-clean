"""Cópias independentes de conteúdo. Nunca copia atividades ou acessos de alunos."""
import logging

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app import models as m
from app.aulas import validar_conclusao


def filhos(db, modelo, **vinculo):
    return db.query(modelo).filter_by(**vinculo).order_by(modelo.id).all()


def novo(db, origem, campos, **vinculo):
    valores = {campo: getattr(origem, campo) for campo in campos}
    valores.update(vinculo)
    registro = type(origem)(**valores)
    db.add(registro)
    db.flush()
    return registro


def copiar_assunto_conteudo(db, origem, disciplina_id, ordem=None):
    assunto = novo(db, origem, ('nome', 'descricao', 'ativo', 'ordem'),
                   curso_disciplina_propria_id=disciplina_id,
                   ordem=origem.ordem if ordem is None else ordem)
    for pasta_origem in filhos(db, m.Pasta, curso_assunto_proprio_id=origem.id):
        pasta = novo(db, pasta_origem, ('tipo', 'nome'), assunto_id=None,
                     curso_assunto_proprio_id=assunto.id)
        for aula_origem in filhos(db, m.Aula, pasta_id=pasta_origem.id):
            aula = novo(db, aula_origem, ('titulo', 'descricao', 'ordem', 'ativo'), pasta_id=pasta.id)
            for video in filhos(db, m.Video, aula_id=aula_origem.id):
                novo(db, video, ('titulo', 'url', 'provedor', 'cloudflare_uid',
                                'duracao_segundos', 'transcricao', 'ordem', 'ativo'), aula_id=aula.id)
            for material in filhos(db, m.Material, aula_id=aula_origem.id):
                novo(db, material, ('tipo', 'titulo', 'url', 'conteudo', 'ordem', 'ativo'), aula_id=aula.id)
            for bateria_origem in filhos(db, m.Bateria, aula_id=aula_origem.id):
                bateria = novo(db, bateria_origem, ('titulo', 'ordem', 'status', 'ativo'), aula_id=aula.id)
                for questao_origem in filhos(db, m.Questao, bateria_id=bateria_origem.id):
                    questao = novo(db, questao_origem, ('enunciado', 'tipo', 'ordem', 'ativo',
                                                      'tipo_questao', 'quantidade_alternativas',
                                                      'gabarito', 'comentario'), bateria_id=bateria.id)
                    mapa = {}
                    for alternativa in filhos(db, m.Alternativa, questao_id=questao_origem.id):
                        copia = novo(db, alternativa, ('letra', 'texto'), questao_id=questao.id)
                        mapa[alternativa.id] = copia.id
                    for comentario in filhos(db, m.Comentario, questao_id=questao_origem.id):
                        novo(db, comentario, ('texto',), questao_id=questao.id,
                             alternativa_id=mapa.get(comentario.alternativa_id))
    for pratica_origem in filhos(db, m.QuestaoPraticaAssunto, curso_assunto_proprio_id=origem.id):
        pratica = novo(db, pratica_origem, ('tipo', 'enunciado', 'gabarito', 'comentario', 'ativo'),
                       curso_assunto_proprio_id=assunto.id)
        for alternativa in filhos(db, m.QuestaoPraticaAlternativa, questao_pratica_id=pratica_origem.id):
            novo(db, alternativa, ('letra', 'texto', 'correta'), questao_pratica_id=pratica.id)
    return assunto


def copiar_disciplina_conteudo(db, origem, curso_id, ordem=None):
    disciplina = novo(db, origem, ('nome', 'ativo', 'ordem', 'disponivel_demonstracao'),
                      curso_id=curso_id, ordem=origem.ordem if ordem is None else ordem)
    for assunto in filhos(db, m.CursoAssuntoProprio, curso_disciplina_propria_id=origem.id):
        copiar_assunto_conteudo(db, assunto, disciplina.id)
    return disciplina


def bloquear_registro(db, modelo, identificador, descricao):
    registro = (db.query(modelo).filter_by(id=identificador).populate_existing()
                .with_for_update().first())
    if registro is None:
        raise HTTPException(404, f'{descricao} não encontrado(a).')
    return registro


def bloquear_cursos(db, origem_id, destino_id):
    # Ordem determinística também para cópias simultâneas em sentidos opostos.
    cursos = (db.query(m.Curso).filter(m.Curso.id.in_({origem_id, destino_id}))
              .order_by(m.Curso.id).populate_existing().with_for_update().all())
    por_id = {curso.id: curso for curso in cursos}
    if origem_id not in por_id or destino_id not in por_id:
        raise HTTPException(404, 'Curso de origem ou destino não encontrado.')
    if not por_id[destino_id].ativo:
        raise HTTPException(400, 'O curso de destino está inativo.')
    return por_id[destino_id]


def filhos_bloqueados(db, modelo, **vinculo):
    return (db.query(modelo).filter_by(**vinculo).order_by(modelo.id)
            .populate_existing().with_for_update().all())


def validar_ordens(registros, descricao):
    ordens = [r.ordem for r in registros]
    if len(set(ordens)) != len(ordens) or any(ordem is None or ordem < 1 for ordem in ordens):
        raise HTTPException(409, f'{descricao} de origem possuem ordens inválidas ou repetidas; revise a estrutura.')


def validar_assunto_copia(db, assunto):
    pastas = filhos_bloqueados(db, m.Pasta, curso_assunto_proprio_id=assunto.id)
    if len(pastas) != 1 or pastas[0].tipo != 'TEORIA' or pastas[0].assunto_id is not None:
        raise HTTPException(409, 'O assunto de origem deve possuir uma única pasta TEORIA vinculada à estrutura própria do curso.')
    aulas = filhos_bloqueados(db, m.Aula, pasta_id=pastas[0].id)
    if len(aulas) > 1:
        raise HTTPException(409, 'A pasta de origem possui mais de uma aula técnica; revise sua estrutura.')
    # Uma pasta ainda sem aula é um cadastro em preparação; não inventar uma aula.
    for aula in aulas:
        for modelo, descricao in ((m.Video, 'Vídeos'), (m.Material, 'Materiais'), (m.Bateria, 'Baterias')):
            registros = filhos_bloqueados(db, modelo, aula_id=aula.id)
            if len(registros) > 20:
                raise HTTPException(409, f'{descricao} de origem excedem o limite de 20 por aula.')
            validar_ordens(registros, descricao)
            if modelo is not m.Bateria:
                continue
            for bateria in registros:
                questoes = filhos_bloqueados(db, m.Questao, bateria_id=bateria.id)
                if len(questoes) > 10:
                    raise HTTPException(409, 'A bateria de origem excede o limite de 10 questões.')
                if bateria.status not in {'EM_ANDAMENTO', 'CONCLUIDA'}:
                    raise HTTPException(409, 'A bateria de origem possui status incompatível.')
                validar_ordens(questoes, 'Questões')
                for questao in questoes:
                    alternativas = filhos_bloqueados(db, m.Alternativa, questao_id=questao.id)
                    comentarios = filhos_bloqueados(db, m.Comentario, questao_id=questao.id)
                    ids = {a.id for a in alternativas}
                    if any(c.alternativa_id is not None and c.alternativa_id not in ids for c in comentarios):
                        raise HTTPException(409, 'Há comentário de conteúdo vinculado a alternativa de outra questão.')
                if bateria.status == 'CONCLUIDA':
                    try:
                        validar_conclusao(db, bateria)
                    except HTTPException as erro:
                        raise HTTPException(409, f'Bateria concluída de origem incompatível: {erro.detail}') from erro
    for pratica in filhos_bloqueados(db, m.QuestaoPraticaAssunto, curso_assunto_proprio_id=assunto.id):
        filhos_bloqueados(db, m.QuestaoPraticaAlternativa, questao_pratica_id=pratica.id)


def proxima_ordem(db, modelo, **vinculo):
    maior = db.query(func.max(modelo.ordem)).filter(
        *(getattr(modelo, campo) == valor for campo, valor in vinculo.items())
    ).scalar()
    return max(maior or 0, 0) + 1


def copiar_disciplina_para_curso(db, disciplina_id, curso_destino_id):
    origem = db.get(m.CursoDisciplinaPropria, disciplina_id)
    if origem is None:
        raise HTTPException(404, 'Disciplina de origem não encontrada.')
    if origem.curso_id == curso_destino_id:
        raise HTTPException(400, 'O curso de destino deve ser diferente do curso de origem.')
    destino = bloquear_cursos(db, origem.curso_id, curso_destino_id)
    origem = bloquear_registro(db, m.CursoDisciplinaPropria, disciplina_id, 'Disciplina de origem')
    assuntos = filhos_bloqueados(db, m.CursoAssuntoProprio, curso_disciplina_propria_id=origem.id)
    validar_ordens(assuntos, 'Assuntos')
    for assunto in assuntos:
        validar_assunto_copia(db, assunto)
    copia = copiar_disciplina_conteudo(db, origem, destino.id,
                                     proxima_ordem(db, m.CursoDisciplinaPropria, curso_id=destino.id))
    return {'ok': True, 'disciplina_origem_id': origem.id,
            'nova_disciplina_id': copia.id, 'nova_disciplina_nome': copia.nome,
            'curso_destino_id': destino.id, 'curso_destino_nome': destino.nome}


def copiar_assunto_para_disciplina(db, assunto_id, disciplina_destino_id):
    origem = db.get(m.CursoAssuntoProprio, assunto_id)
    destino = db.get(m.CursoDisciplinaPropria, disciplina_destino_id)
    if origem is None:
        raise HTTPException(404, 'Assunto de origem não encontrado.')
    if destino is None:
        raise HTTPException(404, 'Disciplina de destino não encontrada.')
    if origem.curso_disciplina_propria_id == destino.id:
        raise HTTPException(400, 'A disciplina de destino deve ser diferente da disciplina de origem.')
    disciplina_origem = db.get(m.CursoDisciplinaPropria, origem.curso_disciplina_propria_id)
    if disciplina_origem is None:
        raise HTTPException(409, 'Assunto de origem sem disciplina própria válida.')
    bloquear_cursos(db, disciplina_origem.curso_id, destino.curso_id)
    for identificador in sorted({disciplina_origem.id, destino.id}):
        bloquear_registro(db, m.CursoDisciplinaPropria, identificador, 'Disciplina')
    origem = bloquear_registro(db, m.CursoAssuntoProprio, assunto_id, 'Assunto de origem')
    validar_assunto_copia(db, origem)
    copia = copiar_assunto_conteudo(db, origem, destino.id,
                                  proxima_ordem(db, m.CursoAssuntoProprio, curso_disciplina_propria_id=destino.id))
    return {'ok': True, 'assunto_origem_id': origem.id,
            'novo_assunto_id': copia.id, 'novo_assunto_nome': copia.nome,
            'disciplina_destino_id': destino.id, 'disciplina_destino_nome': destino.nome,
            'curso_destino_id': destino.curso_id}


def executar_copia(db, operacao, descricao):
    try:
        resultado = operacao()
        db.commit()
        return resultado
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Conflito de integridade ao copiar; nenhuma cópia foi gravada.')
    except Exception:
        db.rollback()
        logging.getLogger(__name__).exception('Falha ao copiar %s', descricao)
        raise HTTPException(500, f'Falha ao copiar {descricao}; nenhuma cópia foi gravada.')
