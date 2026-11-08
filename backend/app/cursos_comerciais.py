"""Publicação comercial não altera direitos; exclusão lógica protege o histórico."""
from fastapi import HTTPException
from sqlalchemy import or_, select
from app import models as m

VENDA_DESATIVADA = 'A venda deste curso está desativada. Somente renovações válidas e pagamentos já iniciados podem continuar.'
EXCLUSAO_BLOQUEADA = 'Este curso possui vínculos acadêmicos ou financeiros e não pode ser excluído. Utilize Desativar venda para preservar os direitos dos alunos e o histórico.'


def bloquear_curso(db, curso_id, exigir_ativo=False, aquisicao=False):
    # Aquisições de alunos diferentes compartilham o lock. Publicação e
    # exclusão usam FOR UPDATE, que aguarda essas admissões terminarem.
    curso = db.query(m.Curso).filter_by(id=curso_id).populate_existing().with_for_update(
        read=aquisicao, key_share=aquisicao).first()
    if not curso or (exigir_ativo and not curso.ativo):
        raise HTTPException(404, 'Curso não encontrado')
    return curso


def garantir_exclusao_segura(db, curso):
    # Não restringir a vigência/status: histórico, concessões expiradas, intenção
    # de compra e pagamentos pendentes também impedem a exclusão lógica.
    for modelo in (m.AcessoCurso, m.ContratacaoCurso, m.ConcessaoAcessoAdmin,
                   m.DemonstracaoCurso, m.OportunidadeCompra, m.Pagamento,
                   m.PeriodoAcessoPagamento, m.AceiteJuridico):
        if db.query(modelo.id).filter(modelo.curso_id == curso.id).first():
            raise HTTPException(409, EXCLUSAO_BLOQUEADA)

    disciplinas = select(m.CursoDisciplinaPropria.id).where(m.CursoDisciplinaPropria.curso_id == curso.id)
    assuntos = select(m.CursoAssuntoProprio.id).where(m.CursoAssuntoProprio.curso_disciplina_propria_id.in_(disciplinas))
    # Inclui atividades legadas da estrutura compartilhada por disciplinas.
    legados = select(m.Assunto.id).join(m.curso_disciplina,
        m.curso_disciplina.c.disciplina_id == m.Assunto.disciplina_id).where(m.curso_disciplina.c.curso_id == curso.id)
    pastas = select(m.Pasta.id).where(or_(m.Pasta.curso_assunto_proprio_id.in_(assuntos), m.Pasta.assunto_id.in_(legados)))
    aulas = select(m.Aula.id).where(m.Aula.pasta_id.in_(pastas))
    baterias = select(m.Bateria.id).where(m.Bateria.aula_id.in_(aulas))
    questoes = select(m.Questao.id).where(m.Questao.bateria_id.in_(baterias))
    praticas = select(m.QuestaoPraticaAssunto.id).where(m.QuestaoPraticaAssunto.curso_assunto_proprio_id.in_(assuntos))
    historicos = (
        (m.ProgressoAula, or_(m.ProgressoAula.pasta_id.in_(pastas), m.ProgressoAula.aula_id.in_(aulas))),
        (m.RevisaoAluno, or_(m.RevisaoAluno.pasta_id.in_(pastas), m.RevisaoAluno.aula_id.in_(aulas))),
        (m.TentativaBateria, m.TentativaBateria.bateria_id.in_(baterias)),
        (m.RespostaAlunoQuestao, or_(m.RespostaAlunoQuestao.bateria_id.in_(baterias), m.RespostaAlunoQuestao.questao_id.in_(questoes))),
        (m.AnotacaoAlunoQuestao, or_(m.AnotacaoAlunoQuestao.bateria_id.in_(baterias), m.AnotacaoAlunoQuestao.questao_id.in_(questoes))),
        (m.ConversaQuestaoProfessor, or_(m.ConversaQuestaoProfessor.bateria_id.in_(baterias), m.ConversaQuestaoProfessor.questao_id.in_(questoes))),
        (m.RespostaQuestaoPratica, m.RespostaQuestaoPratica.questao_pratica_id.in_(praticas)),
        (m.QuestaoPraticaMarcacaoAluno, m.QuestaoPraticaMarcacaoAluno.questao_id.in_(praticas)),
        (m.QuestaoPraticaRotatividadeAluno, or_(m.QuestaoPraticaRotatividadeAluno.curso_assunto_proprio_id.in_(assuntos), m.QuestaoPraticaRotatividadeAluno.questao_id.in_(praticas))),
    )
    for modelo, filtro in historicos:
        if db.query(modelo.id).filter(filtro).first():
            raise HTTPException(409, EXCLUSAO_BLOQUEADA)
