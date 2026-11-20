"""Modalidades de demonstração em SQLite descartável."""
from types import SimpleNamespace

import pytest

from app import models as m, schemas
from app.copias import copiar_disciplina_conteudo
from app.desempenho import consultar
from app.disponibilidade_demonstracao import sincronizar
from test_questoes_pratica_patch import carregar_main_isolado
from test_revisoes_assunto import env


@pytest.mark.parametrize('por_ordem', [False, True])
def test_desempenho_revisao_e_navegacao_com_marcadores_divergentes(env, por_ordem):
    db, client = env
    curso = db.get(m.Curso, 1)
    curso.demonstracao_por_ordem = por_ordem
    primeira = db.get(m.CursoDisciplinaPropria, 1)
    primeira.disponivel_demonstracao = False
    db.add_all([
        m.CursoDisciplinaPropria(id=2, curso_id=1, nome='Segunda', ordem=2, disponivel_demonstracao=False),
        m.CursoDisciplinaPropria(id=3, curso_id=1, nome='Terceira', ordem=3, disponivel_demonstracao=True),
    ])
    db.commit()
    nomes = [d['nome'] for d in consultar(db, 1, 1, None, 1)['disciplinas']]
    assert nomes == (['Disciplina', 'Segunda'] if por_ordem else ['Terceira'])
    resposta = client.get('/me/revisoes/1?demonstracao_id=1')
    assert resposta.status_code == (200 if por_ordem else 403)
    with carregar_main_isolado(lambda: db, db.bind) as main:
        aluno = SimpleNamespace(id=1, is_admin=False)
        disciplinas = main.listar_disciplinas_proprias(1, None, 1, db, aluno)
        assert [d['bloqueada'] for d in disciplinas] == [False, False, True]
    primeira.ordem = 4
    db.flush()
    sincronizar(db, 1)
    db.commit()
    nomes = [d['nome'] for d in consultar(db, 1, 1, None, 1)['disciplinas']]
    assert nomes == (['Segunda', 'Terceira'] if por_ordem else ['Terceira'])
    assert client.get('/me/revisoes/1?demonstracao_id=1').status_code == 403
    assert [db.get(m.CursoDisciplinaPropria, i).disponivel_demonstracao for i in (1, 2, 3)] == (
        [False, True, True] if por_ordem else [False, False, True])


@pytest.mark.parametrize('por_ordem', [False, True])
def test_criar_editar_desativar_e_excluir_respeita_modalidade(env, por_ordem):
    db, _ = env
    db.get(m.Curso, 1).demonstracao_por_ordem = por_ordem
    db.get(m.CursoDisciplinaPropria, 1).disponivel_demonstracao = not por_ordem
    db.commit()
    admin = SimpleNamespace(id=1, is_admin=True, tipo_admin='admin_geral')
    with carregar_main_isolado(lambda: db, db.bind) as main:
        d2 = main.criar_disciplina_propria(1, schemas.CursoDisciplinaPropriaCreate(
            curso_id=1, nome='Segunda', ordem=2), db, admin)
        d3 = main.criar_disciplina_propria(1, schemas.CursoDisciplinaPropriaCreate(
            curso_id=1, nome='Terceira', ordem=3), db, admin)
        ids = (1, d2.id, d3.id)
        def flags():
            return [db.get(m.CursoDisciplinaPropria, i).disponivel_demonstracao for i in ids]
        assert flags() == ([True, True, False] if por_ordem else [True, False, False])
        main.editar_disciplina_propria(d3.id, schemas.CursoDisciplinaPropriaUpdate(ordem=0), db, admin)
        assert flags() == ([True, False, True] if por_ordem else [True, False, False])
        main.editar_disciplina_propria(d3.id, schemas.CursoDisciplinaPropriaUpdate(ativo=False), db, admin)
        assert flags() == ([True, True, False] if por_ordem else [True, False, False])
        main.excluir_disciplina_propria(d3.id, db, admin)
        assert [db.get(m.CursoDisciplinaPropria, i).disponivel_demonstracao for i in ids[:2]] == (
            [True, True] if por_ordem else [True, False])


@pytest.mark.parametrize('destino_por_ordem', [False, True])
def test_copia_entre_cursos_obedece_modalidade_do_destino(env, destino_por_ordem):
    db, _ = env
    db.add(m.Curso(id=2, nome='Destino', demonstracao_por_ordem=destino_por_ordem))
    db.add_all([
        m.CursoDisciplinaPropria(id=2, curso_id=2, nome='Existente 1', ordem=2, disponivel_demonstracao=False),
        m.CursoDisciplinaPropria(id=3, curso_id=2, nome='Existente 2', ordem=3, disponivel_demonstracao=True),
        m.CursoDisciplinaPropria(id=4, curso_id=1, nome='Origem', ordem=1, disponivel_demonstracao=False),
    ])
    db.flush()
    nova = copiar_disciplina_conteudo(db, db.get(m.CursoDisciplinaPropria, 4), 2, ordem=1)
    db.flush()
    assert nova.disponivel_demonstracao is destino_por_ordem
    assert db.get(m.CursoDisciplinaPropria, 2).disponivel_demonstracao is destino_por_ordem
    assert db.get(m.CursoDisciplinaPropria, 3).disponivel_demonstracao is (not destino_por_ordem)
