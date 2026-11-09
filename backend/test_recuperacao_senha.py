"""Rotas reais, SQLite em memória e Resend simulado; nenhum envio externo."""
import hashlib
import re
import socket
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

import pytest
import requests
import resend
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models as m
from test_questoes_pratica_patch import carregar_main_isolado


@pytest.fixture
def recuperacao(monkeypatch):
    def rede_proibida(*args, **kwargs):
        raise AssertionError('Acesso externo proibido neste teste')

    monkeypatch.setattr(socket.socket, 'connect', rede_proibida)
    monkeypatch.setattr(requests.sessions.Session, 'request', rede_proibida)
    monkeypatch.setenv('SECRET_KEY', 'segredo-exclusivamente-sintetico-recuperacao-2026')
    monkeypatch.setenv('RESEND_API_KEY', 're_chave_sintetica_sem_acesso')
    monkeypatch.setenv('APP_BASE_URL', 'https://plataforma.example')
    monkeypatch.setenv('EMAILS_PAGAMENTOS_ATIVOS', 'false')
    # A recuperação deve usar o remetente próprio, sem consumir o de pagamentos.
    monkeypatch.setenv('RESEND_FROM_EMAIL', 'Pagamentos <fila@example.invalid>')
    monkeypatch.setattr(resend, 'api_key', 're_chave_sintetica_sem_acesso')
    envio = Mock(return_value={'id': 'envio-simulado'})
    monkeypatch.setattr(resend.Emails, 'send', envio)
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False},
                           poolclass=StaticPool)
    factory = sessionmaker(bind=engine)
    m.Base.metadata.create_all(engine, tables=[
        m.Usuario.__table__, m.TokenRecuperacaoSenha.__table__])
    try:
        with carregar_main_isolado(factory, engine) as main:
            senha_hash = main.hash_senha('Anterior123')
            with factory() as db:
                db.add(m.Usuario(id=1, nome='Aluna Fictícia',
                    email='aluna@example.invalid', cpf='12345678901', telefone='000',
                    senha_hash=senha_hash, tentativas_login=2, bloqueado_login=True))
                db.add(m.TokenRecuperacaoSenha(usuario_id=1,
                    token_hash=hashlib.sha256(b'token-anterior-ficticio').hexdigest(),
                    expira_em=datetime.utcnow() + timedelta(minutes=10), usado=False))
                db.commit()

            yield SimpleNamespace(main=main, factory=factory,
                                  envio=envio, senha_hash=senha_hash)
    finally:
        engine.dispose()


def solicitar(env, login):
    with env.factory() as db:
        return env.main.recuperar_senha(env.main.RecuperarSenhaRequest(login=login), db)


def redefinir(env, token, senha='NovaSenha123'):
    with env.factory() as db:
        return env.main.redefinir_senha(
            env.main.RedefinirSenhaRequest(token=token, nova_senha=senha), db)


def token_enviado(env):
    payload = env.envio.call_args.args[0]
    link = re.search(r'href="([^"]+)"', payload['html']).group(1)
    partes = urlsplit(link)
    assert partes.scheme == 'https' and partes.netloc == 'plataforma.example'
    assert partes.path == '/redefinir-senha.html'
    token = parse_qs(partes.query)['token'][0]
    assert re.fullmatch(r'[A-Za-z0-9_-]{43}', token)
    return token


def conferir_dados_preservados(env):
    with env.factory() as db:
        aluno = db.get(m.Usuario, 1)
        assert aluno.email == 'aluna@example.invalid'
        assert aluno.nome == 'Aluna Fictícia'
        assert aluno.senha_hash == env.senha_hash
        assert aluno.tentativas_login == 2 and aluno.bloqueado_login is True
        anterior = db.query(m.TokenRecuperacaoSenha).filter_by(
            token_hash=hashlib.sha256(b'token-anterior-ficticio').hexdigest()).one()
        assert anterior.usado is False


@pytest.mark.parametrize('login', [' ALUNA@example.invalid ', '123.456.789-01'])
def test_envio_identidade_e_token_persistido(recuperacao, login):
    env = recuperacao
    antes = datetime.utcnow()
    resposta = solicitar(env, login)
    depois = datetime.utcnow()
    assert resposta == {
        'ok': True, 'message': 'Verifique seu e-mail para redefinir sua senha!'}
    env.envio.assert_called_once()
    payload = env.envio.call_args.args[0]
    assert payload['from'] == 'Resumão Online <contato@resumaoonline.com.br>'
    assert payload['subject'] == 'Redefinição de senha - Resumão Online'
    assert payload['to'] == ['aluna@example.invalid']
    assert 'Resumão Online' in payload['html']
    assert 'Quality Estudos' not in payload['html']
    assert '30 minutos' in payload['html']
    assert '<h2>' not in payload['html']
    texto = ' '.join(re.sub(r'<[^>]+>', ' ', payload['html']).split())
    assert texto == (
        'Olá, Aluna Fictícia! '
        'Recebemos uma solicitação para redefinir a senha da sua conta no Resumão Online. '
        'Redefinir minha senha Este link é válido por 30 minutos. '
        'Se você não solicitou a redefinição, ignore este e-mail.'
    )
    token = token_enviado(env)
    assert token not in str(resposta)
    with env.factory() as db:
        assert db.query(m.TokenRecuperacaoSenha).count() == 2
        registro = db.query(m.TokenRecuperacaoSenha).filter_by(
            token_hash=hashlib.sha256(token.encode()).hexdigest()).one()
        assert registro.usuario_id == 1 and registro.usado is False
        assert registro.usado_em is None
        assert antes + timedelta(minutes=30) <= registro.expira_em <= depois + timedelta(minutes=30)
        assert registro.token_hash != token
    conferir_dados_preservados(env)


@pytest.mark.parametrize('falha', ['envio', 'persistencia'])
def test_falhas_revertem_apenas_novo_token(recuperacao, falha):
    env = recuperacao
    if falha == 'envio':
        env.envio.side_effect = RuntimeError('falha de envio simulada')
        contexto = patch.object(env.main.resend.Emails, 'send', env.envio)
    else:
        # Simula falha depois do INSERT/flush; rollback deve desfazer a gravação.
        def commit_falhando(db):
            db.flush()
            raise RuntimeError('falha de persistência simulada')
        contexto = patch.object(env.factory.class_, 'commit', commit_falhando)
    with contexto, pytest.raises(HTTPException) as erro:
        solicitar(env, 'aluna@example.invalid')
    assert erro.value.status_code == 500
    assert erro.value.detail == (
        'Não foi possível enviar o e-mail de recuperação. Tente novamente mais tarde.')
    assert 'simulada' not in erro.value.detail
    env.envio.assert_called_once()
    with env.factory() as db:
        assert db.query(m.TokenRecuperacaoSenha).count() == 1
    conferir_dados_preservados(env)
    if falha == 'persistencia':
        token = token_enviado(env)
        with pytest.raises(HTTPException) as erro:
            redefinir(env, token)
        assert erro.value.status_code == 400
        conferir_dados_preservados(env)


@pytest.mark.parametrize('login,tipo', [
    ('ausente@example.invalid', 'email'), ('00000000000', 'CPF')])
def test_conta_ausente_nao_envia_nem_grava(recuperacao, login, tipo):
    env = recuperacao
    with pytest.raises(HTTPException) as erro:
        solicitar(env, login)
    assert erro.value.status_code == 404
    assert tipo in erro.value.detail
    env.envio.assert_not_called()
    with env.factory() as db:
        assert db.query(m.TokenRecuperacaoSenha).count() == 1
    conferir_dados_preservados(env)


def test_token_utilizavel_uma_vez(recuperacao):
    env = recuperacao
    assert solicitar(env, 'aluna@example.invalid')['ok'] is True
    token = token_enviado(env)
    assert redefinir(env, token)['ok'] is True
    with env.factory() as db:
        aluno = db.get(m.Usuario, 1)
        assert env.main.verificar_senha('NovaSenha123', aluno.senha_hash)
        assert aluno.tentativas_login == 0 and aluno.bloqueado_login is False
        registro = db.query(m.TokenRecuperacaoSenha).filter_by(
            token_hash=hashlib.sha256(token.encode()).hexdigest()).one()
        assert registro.usado is True and registro.usado_em is not None
    with pytest.raises(HTTPException) as erro:
        redefinir(env, token)
    assert erro.value.status_code == 400
    env.envio.assert_called_once()


@pytest.mark.parametrize('estado', ['expirado', 'invalido'])
def test_tokens_rejeitados_preservam_senha(recuperacao, estado):
    env = recuperacao
    assert solicitar(env, 'aluna@example.invalid')['ok'] is True
    token = token_enviado(env)
    if estado == 'expirado':
        with env.factory() as db:
            registro = db.query(m.TokenRecuperacaoSenha).filter_by(
                token_hash=hashlib.sha256(token.encode()).hexdigest()).one()
            registro.expira_em = datetime.utcnow() - timedelta(seconds=1)
            db.commit()
    else:
        token = 'token-invalido-ficticio'
    with pytest.raises(HTTPException) as erro:
        redefinir(env, token)
    assert erro.value.status_code == 400
    conferir_dados_preservados(env)
