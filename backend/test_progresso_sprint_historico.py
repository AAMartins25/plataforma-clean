"""Fluxos HTTP em SQLite descartável, sem pagamentos reais."""
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app import models as m
from test_progresso_agregado import ambiente


def entrar(client, email):
    resposta = client.post('/login', data={'username': email, 'password': 'SenhaTeste123!'})
    assert resposta.status_code == 200, resposta.text
    return {'Authorization': 'Bearer ' + resposta.json()['access_token']}


def aluno_e_contratacao(db, main, origem):
    db.add(m.Usuario(id=40, nome='Aluno sintético', email='sintetico@example.test',
                     cpf='12345678901', telefone='0', senha_hash=main.hash_senha('SenhaTeste123!'),
                     ativo=True, is_admin=False))
    db.add(m.ContratacaoCurso(id=40, usuario_id=40, curso_id=1, origem=origem,
                             data_inicio=datetime.utcnow() - timedelta(days=1)))


@pytest.mark.parametrize('origem', ['ADMIN', 'PAGAMENTO'])
def test_novo_login_outro_cliente_e_refazer(ambiente, origem):
    main, _, factory, _ = ambiente
    with factory() as db:
        aluno_e_contratacao(db, main, origem)
        db.add(m.ContratacaoCurso(id=41, usuario_id=40, curso_id=1, origem=origem,
                                 data_inicio=datetime.utcnow() - timedelta(days=1)))
        db.add_all([
            m.TentativaBateria(id=40, usuario_id=40, bateria_id=1, contratacao_id=40,
                               status='FEITA', ativo=True),
            m.TentativaBateria(id=41, usuario_id=40, bateria_id=2, contratacao_id=40,
                               status='FEITA', ativo=True),
        ])
        db.commit()

    def percentuais(client, headers):
        valores = []
        for url in ('/me/disciplinas-proprias/1/progresso-assuntos',
                    '/me/cursos/1/progresso-disciplinas'):
            resposta = client.get(url, params={'contratacao_id': 40}, headers=headers)
            assert resposta.status_code == 200, resposta.text
            valores.append(resposta.json()['percentuais'][0]['percentual'])
        return valores

    primeiro = TestClient(main.app)
    assert percentuais(primeiro, entrar(primeiro, 'sintetico@example.test')) == [100, 67]
    segundo = TestClient(main.app)
    headers = entrar(segundo, 'sintetico@example.test')
    assert percentuais(segundo, headers) == [100, 67]
    outra = segundo.get('/me/disciplinas-proprias/1/progresso-assuntos',
                        params={'contratacao_id': 41}, headers=headers)
    assert outra.status_code == 200 and outra.json()['percentuais'][0]['percentual'] == 0
    resposta = segundo.put('/baterias/1/limpar-minha-sprint',
                           params={'contratacao_id': 40}, headers=headers)
    assert resposta.status_code == 200, resposta.text
    assert percentuais(segundo, headers) == [100, 67]

    with factory() as db:
        db.add(m.TentativaBateria(id=42, usuario_id=40, bateria_id=1, contratacao_id=40,
                                   status='EM_ANDAMENTO', ativo=True))
        db.commit()
    assert percentuais(segundo, headers) == [100, 67]
    with factory() as db:
        # Conclusões sucessivas não devem ser contadas mais de uma vez.
        db.add_all([
            m.TentativaBateria(id=43, usuario_id=40, bateria_id=1, contratacao_id=40,
                               status='FEITA', ativo=False),
            m.TentativaBateria(id=44, usuario_id=40, bateria_id=1, contratacao_id=40,
                               status='FEITA', ativo=True),
        ])
        db.commit()
    terceiro = TestClient(main.app)
    assert percentuais(terceiro, entrar(terceiro, 'sintetico@example.test')) == [100, 67]
    with factory() as db:
        original = db.get(m.TentativaBateria, 40)
        assert original.status == 'FEITA' and not original.ativo


@pytest.mark.parametrize('origem', ['ADMIN', 'PAGAMENTO'])
def test_gravacao_e_finalizacao_recarregamento(ambiente, origem):
    main, _, factory, _ = ambiente
    with factory() as db:
        aluno_e_contratacao(db, main, origem)
        db.add(m.CursoAssuntoProprio(id=10, curso_disciplina_propria_id=1, nome='Outro'))
        db.add(m.Pasta(id=10, curso_assunto_proprio_id=10, tipo='TEORIA', nome='Teoria'))
        db.add(m.Aula(id=10, pasta_id=10, titulo='Aula', ativo=True))
        db.add(m.Bateria(id=10, aula_id=10, titulo='Sprint', status='CONCLUIDA', ativo=True))
        db.add_all([
            m.Questao(id=i, bateria_id=10, enunciado='Teste', tipo='CERTO_ERRADO',
                      tipo_questao='CERTO_ERRADO', gabarito='C', ordem=i, ativo=True)
            for i in range(100, 110)
        ])
        db.commit()

    def percentual(client, headers):
        resposta = client.get('/me/disciplinas-proprias/1/progresso-assuntos',
                              params={'contratacao_id': 40}, headers=headers)
        assert resposta.status_code == 200, resposta.text
        return next(x['percentual'] for x in resposta.json()['percentuais'] if x['assunto_id'] == 10)

    primeiro = TestClient(main.app)
    headers = entrar(primeiro, 'sintetico@example.test')
    assert percentual(primeiro, headers) == 0
    payload = {'bateria_id': 10, 'contratacao_id': 40, 'respostas': [
        {'questao_id': i, 'resposta_marcada': 'C'} for i in range(100, 110)
    ]}
    resposta = primeiro.post('/baterias/concluir', json=payload, headers=headers)
    assert resposta.status_code == 200, resposta.text
    tentativa_id = resposta.json()['id']
    assert resposta.json()['status'] == 'EM_ANDAMENTO'
    assert percentual(primeiro, headers) == 0

    segundo = TestClient(main.app)
    headers = entrar(segundo, 'sintetico@example.test')
    resposta = segundo.get('/baterias/10/minha-tentativa-ativa',
                           params={'contratacao_id': 40}, headers=headers)
    assert resposta.status_code == 200
    assert resposta.json()['tentativa']['id'] == tentativa_id
    assert len(resposta.json()['respostas']) == 10
    resposta = segundo.put(f'/tentativas/{tentativa_id}/finalizar-revisao', json={}, headers=headers)
    assert resposta.status_code == 200, resposta.text
    assert percentual(segundo, headers) == 100
    terceiro = TestClient(main.app)
    assert percentual(terceiro, entrar(terceiro, 'sintetico@example.test')) == 100
