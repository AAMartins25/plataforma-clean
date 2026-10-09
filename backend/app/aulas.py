"""Validações de gestão de conteúdo, sem alterar as regras de estudo dos alunos."""
from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app import models as m


def bloquear_pai(db, modelo, identificador):
    registro = db.query(modelo).filter(modelo.id == identificador).with_for_update().first()
    if registro is None:
        raise HTTPException(404, "Aula ou bateria não encontrada")
    return registro


def ordem_conteudo(db, modelo, campo_pai, pai_id, dados, registro=None):
    query = db.query(modelo).filter(campo_pai == pai_id)
    if registro is not None:
        query = query.filter(modelo.id != registro.id)
    if "ordem" in dados.model_fields_set:
        ordem = dados.ordem
    elif registro is not None:
        ordem = registro.ordem
    else:
        ordem = (query.with_entities(func.max(modelo.ordem)).scalar() or 0) + 1
    if ordem < 1:
        raise HTTPException(400, "A ordem deve ser positiva")
    if query.filter(modelo.ordem == ordem).first():
        raise HTTPException(409, "Já existe conteúdo com esta ordem. Escolha outra ordem.")
    return ordem


def confirmar_conteudo(db, flush=False):
    try:
        if flush:
            db.flush()
        else:
            db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Não foi possível salvar: existem vínculos ou conflitos de conteúdo.")


def validar_vinculo(dados, registro, campo):
    if getattr(dados, campo) != getattr(registro, campo):
        raise HTTPException(400, "O conteúdo não pode ser transferido para outra aula ou bateria pela edição.")


def validar_material(dados):
    tipo = dados.tipo.strip().upper()
    if not dados.titulo.strip() or tipo not in {"TEXTO", "PDF", "LINK"}:
        raise HTTPException(400, "Informe título e tipo de material válidos")
    if tipo == "TEXTO" and not (dados.conteudo or "").strip():
        raise HTTPException(400, "Informe o conteúdo do texto")
    if tipo in {"PDF", "LINK"} and not (dados.url or "").strip():
        raise HTTPException(400, "Informe a URL do material")
    return tipo


def garantir_sem_historico(db, bateria):
    # Não apaga nem desativa atividades. Revisões dependem do conjunto da aula.
    for modelo in (m.TentativaBateria, m.RespostaAlunoQuestao,
                   m.AnotacaoAlunoQuestao, m.ConversaQuestaoProfessor):
        if db.query(modelo.id).filter(modelo.bateria_id == bateria.id).first():
            raise HTTPException(409, "Operação bloqueada: a bateria possui histórico de alunos. Os registros devem ser preservados.")
    if db.query(m.RevisaoAluno.id).filter(m.RevisaoAluno.aula_id == bateria.aula_id).first():
        raise HTTPException(409, "Operação bloqueada: a aula possui Revisões programadas ou históricas. Os registros devem ser preservados.")


def validar_alternativas(dados, questao=None):
    tipo = (dados.tipo_questao or "").strip().upper()
    letras = {"MULTIPLA_5": list("ABCDE"), "MULTIPLA_4": list("ABCD"),
              "CERTO_ERRADO": list("CE")}.get(tipo)
    if letras is None or (dados.gabarito or "").strip().upper() not in letras:
        raise HTTPException(400, "Tipo ou gabarito inválido para a questão")
    if not dados.enunciado.strip():
        raise HTTPException(400, "Informe o enunciado da questão")
    alternativas = dados.alternativas
    if alternativas is None:
        if questao is not None and tipo != questao.tipo_questao:
            raise HTTPException(400, "Envie as alternativas ao alterar o tipo de questão")
        return None  # Compatibilidade com cadastro incremental de rascunhos.
    if tipo == "CERTO_ERRADO":
        if alternativas:
            raise HTTPException(400, "Questões CERTO/ERRADO não possuem alternativas cadastradas")
    elif (sorted(a.letra.strip().upper() for a in alternativas) != letras
          or any(not a.texto.strip() for a in alternativas)):
        raise HTTPException(400, "Envie exatamente as alternativas do tipo selecionado, com textos não vazios")
    return alternativas


def sincronizar_alternativas(db, questao, alternativas):
    if alternativas is None:
        return
    existentes = db.query(m.Alternativa).filter_by(questao_id=questao.id).all()
    por_letra = {a.letra: a for a in existentes}
    letras = {a.letra.strip().upper() for a in alternativas}
    for antiga in existentes:
        if antiga.letra not in letras:
            db.query(m.Comentario).filter_by(alternativa_id=antiga.id).delete(synchronize_session=False)
            db.delete(antiga)
    for dados in alternativas:
        letra = dados.letra.strip().upper()
        registro = por_letra.get(letra)
        if registro is None:
            registro = m.Alternativa(questao_id=questao.id, letra=letra)
            db.add(registro)
        registro.texto = dados.texto.strip()


def validar_conclusao(db, bateria):
    questoes = db.query(m.Questao).filter_by(bateria_id=bateria.id).all()
    if len(questoes) != 10:
        raise HTTPException(400, "A bateria precisa ter exatamente 10 questões para ser concluída")
    for questao in questoes:
        tipo = questao.tipo_questao
        letras = {"MULTIPLA_5": list("ABCDE"), "MULTIPLA_4": list("ABCD"),
                  "CERTO_ERRADO": list("CE")}.get(tipo)
        alternativas = db.query(m.Alternativa).filter_by(questao_id=questao.id).all()
        if (letras is None or questao.gabarito not in letras or not questao.enunciado.strip()
                or (tipo == "CERTO_ERRADO" and alternativas)
                or (tipo != "CERTO_ERRADO" and
                    (sorted(a.letra for a in alternativas) != letras
                     or any(not a.texto.strip() for a in alternativas)))):
            raise HTTPException(400, "Complete os tipos, gabaritos e alternativas das 10 questões antes de concluir a bateria")
