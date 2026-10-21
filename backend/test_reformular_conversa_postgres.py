"""Concurrency/integrity coverage against a dedicated disposable PostgreSQL database.

Run only with RESUMAO_TEST_DATABASE_URL pointing at resumao_contexto_teste.
The fixture creates and drops a random schema; it refuses every other database.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
import os
import uuid
from types import SimpleNamespace
from threading import Barrier

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from fastapi import HTTPException

from app import models as m, schemas
from app.pausa_financeira import controle as controle_financeiro
from test_questoes_pratica_patch import carregar_main_isolado


DATABASE_URL = os.environ.get("RESUMAO_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="configure URL do PostgreSQL descartável de testes")

CORE = {
    "cursos", "usuarios", "disciplinas", "assuntos", "curso_disciplinas_proprias",
    "curso_assuntos_proprios", "contratacoes_curso", "demonstracoes_curso", "pastas",
    "aulas", "baterias", "questoes", "revisoes_aluno", "tentativas_bateria",
    "respostas_aluno_questoes", "anotacoes_aluno_questao",
    "conversas_questao_professor", "mensagens_conversa_questao",
}


@pytest.fixture(scope="module")
def pg():
    root = create_engine(DATABASE_URL, pool_pre_ping=True)
    with root.connect() as conn:
        db_name = conn.execute(text("select current_database()")).scalar_one()
        assert db_name == "resumao_contexto_teste", "recusado: banco não é o PostgreSQL descartável autorizado"
        schema = "test_reform_" + uuid.uuid4().hex[:20]
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        conn.commit()

    scoped = create_engine(DATABASE_URL, pool_pre_ping=True,
                           connect_args={"options": f"-csearch_path={schema},public"})
    factory = sessionmaker(bind=scoped, autoflush=False, expire_on_commit=False)
    required = set(CORE)
    changed = True
    while changed:
        changed = False
        for table in m.Base.metadata.tables.values():
            if table.name in required:
                for fk in table.foreign_keys:
                    if fk.column.table.name not in required:
                        required.add(fk.column.table.name)
                        changed = True
    tables = [table for table in m.Base.metadata.sorted_tables
              if table.name in required and table.name != m.ReformulacaoConversaOperacao.__tablename__]
    m.Base.metadata.create_all(scoped, tables=tables)
    controle_financeiro.create(scoped)
    with scoped.begin() as conn:
        conn.execute(controle_financeiro.insert().values(
            id=1, modo="NORMAL", geracao=0, alterado_em=datetime.now(timezone.utc),
            alterado_por=None, motivo="fixture PostgreSQL isolada"
        ))

    # Match the audited production schema, which has no CHECK constraints on these legacy tables.
    with scoped.begin() as conn:
        conn.exec_driver_sql(f'ALTER TABLE "{schema}".conversas_questao_professor DROP CONSTRAINT IF EXISTS conversa_contexto')
        conn.exec_driver_sql(f'ALTER TABLE "{schema}".conversas_questao_professor DROP CONSTRAINT IF EXISTS conversa_status')
        conn.exec_driver_sql(f'ALTER TABLE "{schema}".mensagens_conversa_questao DROP CONSTRAINT IF EXISTS mensagem_autor')

    migration = (Path(__file__).parent / "migrations/020_reformulacao_conversas_idempotencia.sql").read_text()
    migration = migration.replace("SET LOCAL search_path = public, pg_catalog;",
                                  f'SET LOCAL search_path = "{schema}", pg_catalog;')
    migration = migration.replace("public.reformulacoes_conversa_operacoes",
                                  f'"{schema}".reformulacoes_conversa_operacoes')
    raw = scoped.raw_connection()
    try:
        raw.driver_connection.cursor().execute(migration, prepare=False)
        raw.commit()
    finally:
        raw.close()

    with carregar_main_isolado(factory, scoped) as main:
        try:
            yield main, scoped, factory, schema
        finally:
            main.app.dependency_overrides.clear()
            scoped.dispose()
            with root.begin() as conn:
                conn.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
            root.dispose()


@pytest.fixture(autouse=True)
def seeded(pg):
    main, engine, factory, schema = pg
    with engine.begin() as conn:
        conn.exec_driver_sql(f'TRUNCATE TABLE "{schema}".mensagens_conversa_questao, '
            f'"{schema}".conversas_questao_professor, "{schema}".anotacoes_aluno_questao, '
            f'"{schema}".respostas_aluno_questoes, "{schema}".tentativas_bateria, '
            f'"{schema}".revisoes_aluno, "{schema}".questoes, "{schema}".baterias, '
            f'"{schema}".aulas, "{schema}".pastas, "{schema}".curso_assuntos_proprios, '
            f'"{schema}".curso_disciplinas_proprias, "{schema}".assuntos, '
            f'"{schema}".disciplinas, "{schema}".demonstracoes_curso, '
            f'"{schema}".contratacoes_curso, "{schema}".cursos, "{schema}".usuarios, '
            f'"{schema}".reformulacoes_conversa_operacoes RESTART IDENTITY CASCADE')
    db = factory()
    now = datetime.utcnow()
    db.add_all([
        m.Usuario(id=1, nome="Aluno Teste", email="aluno1@example.test", cpf="00000000001", telefone="0", senha_hash="teste"),
        m.Usuario(id=2, nome="Outro Aluno", email="aluno2@example.test", cpf="00000000002", telefone="0", senha_hash="teste"),
        m.Curso(id=1, nome="Curso Teste"),
        m.Disciplina(id=1, nome="Disciplina"),
    ])
    db.flush()
    db.add_all([
        m.Assunto(id=1, disciplina_id=1, nome="Assunto"),
        m.CursoDisciplinaPropria(id=1, curso_id=1, nome="Disciplina do curso", disponivel_demonstracao=True),
        m.DemonstracaoCurso(id=1, usuario_id=1, curso_id=1, data_inicio=now-timedelta(days=1), data_fim=now+timedelta(days=1), liberado_novamente_em=now),
        m.ContratacaoCurso(id=1, usuario_id=1, curso_id=1, origem="ADMIN", data_inicio=now-timedelta(days=1)),
    ])
    db.flush()
    db.add(m.CursoAssuntoProprio(id=1, curso_disciplina_propria_id=1, nome="Assunto do curso"))
    db.flush()
    db.add(m.Pasta(id=1, assunto_id=1, curso_assunto_proprio_id=1, tipo="TEORIA", nome="Teoria"))
    db.flush()
    db.add(m.Aula(id=1, pasta_id=1, titulo="Aula", ativo=True))
    db.flush()
    db.add(m.Bateria(id=1, aula_id=1, titulo="Sprint", status="CONCLUIDA", ativo=True))
    db.flush()
    db.add(m.Questao(id=1, bateria_id=1, enunciado="Questão de teste", tipo="CERTO_ERRADO", tipo_questao="CERTO_ERRADO", gabarito="C", comentario="Comentário"))
    db.flush()
    db.add(m.TentativaBateria(id=1, usuario_id=1, bateria_id=1, demonstracao_id=1, status="FEITA"))
    db.add(m.TentativaBateria(id=2, usuario_id=1, bateria_id=1, contratacao_id=1, status="FEITA"))
    db.flush()
    db.add_all([
        m.RespostaAlunoQuestao(usuario_id=1, bateria_id=1, questao_id=1, tentativa_id=1, demonstracao_id=1, respondida=True, resposta_marcada="NAO_SEI"),
        m.RespostaAlunoQuestao(usuario_id=1, bateria_id=1, questao_id=1, tentativa_id=2, contratacao_id=1, respondida=True, resposta_marcada="C"),
    ])
    db.commit()

    def get_db():
        session = factory()
        try:
            yield session
        finally:
            session.close()
    actor = SimpleNamespace(id=1, is_admin=False)
    main.app.dependency_overrides[main.get_db] = get_db
    main.app.dependency_overrides[main.get_usuario_atual] = lambda: actor
    yield main, factory, db, actor
    db.close()


def create_conversation(main, db, *, attempt=1, contract=False, status="ABERTA"):
    row = m.ConversaQuestaoProfessor(usuario_id=1, questao_id=1, bateria_id=1,
        tentativa_id=attempt, contratacao_id=1 if contract else None,
        demonstracao_id=None if contract else 1, status=status)
    db.add(row); db.flush()
    db.add_all([m.MensagemConversaQuestao(conversa_id=row.id, autor="ALUNO", texto="Pergunta original")])
    if status != "ABERTA":
        db.add(m.MensagemConversaQuestao(conversa_id=row.id, autor="PROFESSOR", texto="Resposta original"))
    db.commit()
    return row.id


def operation_payload(main, db, conversation_id, text_value="Pergunta reformulada", operation_id=None):
    row = db.get(m.ConversaQuestaoProfessor, conversation_id)
    return schemas.ReformularConversaProfessor(
        texto=text_value,
        operacao_id=operation_id or uuid.uuid4(),
        estado_conversa=main._estado_conversa(db, row),
        confirmado=True,
    )


def reform(main, factory, conversation_id, payload, *, user_id=1, contract=False):
    db = factory()
    try:
        return main.reformular_conversa_prof(conversation_id, payload,
            contratacao_id=1 if contract else None,
            demonstracao_id=None if contract else 1,
            db=db, usuario=SimpleNamespace(id=user_id, is_admin=False))
    finally:
        db.close()


def test_postgres_atomic_replacement_preserves_other_study_data(seeded):
    main, factory, db, _ = seeded
    old = create_conversation(main, db)
    db.add(m.AnotacaoAlunoQuestao(usuario_id=1, questao_id=1, bateria_id=1,
        tentativa_id=1, demonstracao_id=1, texto="Anotação deve permanecer")); db.commit()
    payload = operation_payload(main, db, old)
    result = reform(main, factory, old, payload)
    db.expire_all()
    assert result["conversa_id"] != old and result["status"] == "ABERTA"
    assert db.get(m.ConversaQuestaoProfessor, old) is None
    assert db.query(m.MensagemConversaQuestao).filter_by(conversa_id=old).count() == 0
    assert [x.texto for x in db.query(m.MensagemConversaQuestao).filter_by(conversa_id=result["conversa_id"])] == ["Pergunta reformulada"]
    assert db.query(m.TentativaBateria).count() == 2
    assert db.query(m.RespostaAlunoQuestao).count() == 2
    assert db.query(m.AnotacaoAlunoQuestao).one().texto == "Anotação deve permanecer"


def test_postgres_same_operation_is_persistent_and_replayable(seeded):
    main, factory, db, _ = seeded
    old = create_conversation(main, db)
    payload = operation_payload(main, db, old)
    first = reform(main, factory, old, payload)
    second = reform(main, factory, old, payload)
    assert first["conversa_id"] == second["conversa_id"]
    assert db.query(m.ReformulacaoConversaOperacao).count() == 1


def test_postgres_failure_before_commit_rolls_back_every_delete(seeded, monkeypatch):
    main, factory, db, _ = seeded
    old = create_conversation(main, db)
    payload = operation_payload(main, db, old)
    def fail_before_commit(*args, **kwargs):
        raise RuntimeError("simulated failure before commit")
    monkeypatch.setattr(main, "_resultado_conversa", fail_before_commit)
    with pytest.raises(RuntimeError, match="simulated failure"):
        reform(main, factory, old, payload)
    db.expire_all()
    assert db.get(m.ConversaQuestaoProfessor, old) is not None
    assert db.query(m.MensagemConversaQuestao).filter_by(conversa_id=old).count() == 1
    assert db.query(m.ReformulacaoConversaOperacao).count() == 0
    assert db.query(m.ConversaQuestaoProfessor).count() == 1


def test_postgres_parallel_duplicate_operation_has_one_result(seeded):
    main, factory, db, _ = seeded
    old = create_conversation(main, db)
    payload = operation_payload(main, db, old)
    barrier = Barrier(2)
    def request():
        barrier.wait(timeout=5)
        try:
            return reform(main, factory, old, payload)["conversa_id"]
        except HTTPException as exc:
            return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: request(), range(2)))
    assert results[0] == results[1] and results[0] != old
    assert db.query(m.ConversaQuestaoProfessor).count() == 1
    assert db.query(m.MensagemConversaQuestao).count() == 1
    assert db.query(m.ReformulacaoConversaOperacao).count() == 1


def test_postgres_two_tabs_with_distinct_operation_ids_replace_only_once(seeded):
    main, factory, db, _ = seeded
    old = create_conversation(main, db)
    payloads = [operation_payload(main, db, old), operation_payload(main, db, old)]
    barrier = Barrier(2)
    def request(payload):
        barrier.wait(timeout=5)
        try:
            return reform(main, factory, old, payload)["conversa_id"]
        except HTTPException as exc:
            return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(request, payloads))
    assert sum(isinstance(value, int) and value != 404 for value in results) == 1
    assert results.count(404) == 1
    assert db.query(m.ConversaQuestaoProfessor).count() == 1
    assert db.query(m.MensagemConversaQuestao).count() == 1
    assert db.query(m.ReformulacaoConversaOperacao).count() == 1


def test_postgres_reformulation_and_teacher_reply_are_serialized(seeded):
    main, factory, db, _ = seeded
    old = create_conversation(main, db)
    payload = operation_payload(main, db, old)
    barrier = Barrier(2)
    def reform_request():
        barrier.wait(timeout=5)
        try:
            return ("reform", reform(main, factory, old, payload)["conversa_id"])
        except HTTPException as exc:
            return ("reform", exc.status_code)
    def teacher_request():
        barrier.wait(timeout=5)
        session = factory()
        try:
            return ("teacher", main.responder_conversa_prof_admin(old,
                schemas.MensagemProfessorTexto(texto="Nova resposta"),
                db=session, usuario=SimpleNamespace(id=99, is_admin=True)))
        except HTTPException as exc:
            return ("teacher", exc.status_code)
        finally:
            session.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda fn: fn(), (reform_request, teacher_request)))
    r = dict(results)
    if r["reform"] == 409:
        assert r["teacher"]["conversa_id"] == old
        assert db.get(m.ConversaQuestaoProfessor, old) is not None
        assert db.query(m.MensagemConversaQuestao).filter_by(conversa_id=old).count() == 2
    else:
        assert r["reform"] != old
        assert r["teacher"] == 404
        assert db.get(m.ConversaQuestaoProfessor, old) is None


def test_postgres_legacy_rows_stay_out_of_admin_queue(seeded):
    main, factory, db, _ = seeded
    current = create_conversation(main, db)
    legacy = m.ConversaQuestaoProfessor(usuario_id=1, questao_id=1, bateria_id=1,
        tentativa_id=None, contratacao_id=None, demonstracao_id=None, status="ABERTA")
    db.add(legacy); db.flush()
    db.add(m.MensagemConversaQuestao(conversa_id=legacy.id, autor="ALUNO", texto="Legado preservado")); db.commit()
    rows = main.conversas_prof_admin(curso_id=None, disciplina_id=None,
        concluidas=False, db=db, usuario=SimpleNamespace(id=99, is_admin=True))
    assert [item["conversa_id"] for item in rows] == [current]
    assert db.get(m.ConversaQuestaoProfessor, legacy.id) is not None
    assert db.query(m.MensagemConversaQuestao).filter_by(conversa_id=legacy.id).count() == 1


def add_second_attempt_same_context(db):
    db.add(m.TentativaBateria(id=3, usuario_id=1, bateria_id=1,
        demonstracao_id=1, status="FEITA"))
    db.flush()
    db.add(m.RespostaAlunoQuestao(usuario_id=1, bateria_id=1, questao_id=1,
        tentativa_id=3, demonstracao_id=1, respondida=True,
        resposta_marcada="C"))
    db.commit()


def test_postgres_parallel_annotation_across_attempts_conflicts_once(seeded):
    main, factory, db, actor = seeded
    add_second_attempt_same_context(db)
    attempts = (1, 3)
    barrier = Barrier(2)

    def request(attempt):
        session = factory()
        payload = schemas.AnotacaoQuestaoCreate(
            texto="Nota de teste", questao_id=1, bateria_id=1,
            tentativa_id=attempt, demonstracao_id=1)
        barrier.wait(timeout=10)
        try:
            return main.criar_anotacao_questao(payload, db=session,
                usuario_atual=SimpleNamespace(id=1, is_admin=False))
        except HTTPException as exc:
            return exc.status_code
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(request, attempts))
    assert sum(isinstance(result, dict) for result in results) == 1
    assert results.count(409) == 1
    rows = db.query(m.AnotacaoAlunoQuestao).all()
    assert len(rows) == 1
    assert rows[0].tentativa_id in attempts
    assert rows[0].usuario_id == 1 and rows[0].questao_id == 1
    assert rows[0].demonstracao_id == 1 and rows[0].contratacao_id is None


def test_postgres_parallel_conversation_across_attempts_conflicts_once(seeded):
    main, factory, db, actor = seeded
    add_second_attempt_same_context(db)
    attempts = (1, 3)
    barrier = Barrier(2)

    def request(attempt):
        session = factory()
        payload = schemas.ConversaProfessorCreate(
            texto="Pergunta de teste", questao_id=1, bateria_id=1,
            tentativa_id=attempt, demonstracao_id=1)
        barrier.wait(timeout=10)
        try:
            return main.iniciar_conversa_prof(payload, db=session,
                usuario=SimpleNamespace(id=1, is_admin=False))
        except HTTPException as exc:
            return exc.status_code
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(request, attempts))
    assert sum(isinstance(result, dict) for result in results) == 1
    assert results.count(409) == 1
    rows = db.query(m.ConversaQuestaoProfessor).all()
    assert len(rows) == 1
    assert rows[0].tentativa_id in attempts
    assert rows[0].usuario_id == 1 and rows[0].questao_id == 1
    assert rows[0].demonstracao_id == 1 and rows[0].contratacao_id is None
    assert db.query(m.MensagemConversaQuestao).filter_by(conversa_id=rows[0].id).count() == 1
