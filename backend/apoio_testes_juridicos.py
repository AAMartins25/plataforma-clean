"""Compatibilidade das fixtures jurídicas com a main local e o checkout mais recente.
Não altera nem importa configurações de banco; todas as chamadas MP continuam simuladas.
"""
from datetime import datetime
from unittest.mock import Mock
from app import models as m


def preparar(ambiente):
    if hasattr(m.Pagamento, 'checkout_identidade'):
        from test_transacoes_mp import preparar as preparar_atual
        return preparar_atual(ambiente)
    _, cliente, factory, _, get = ambiente
    resposta = cliente.post('/checkout/mercadopago', json={'tempo_acesso_id': 1})
    assert resposta.status_code == 200, resposta.text
    pid = resposta.json()['pagamento_id']
    with factory() as db:
        pagamento = db.get(m.Pagamento, pid)
        valor = pagamento.valor_cents / 100
    def dados(tx, status='pending'):
        return {'id': str(tx), 'status': status, 'payment_method_id': 'pix',
                'transaction_amount': valor, 'currency_id': 'BRL',
                'date_approved': datetime.utcnow().isoformat()+'Z',
                'external_reference': f'user:1|curso:1|tempo:1|pagamento:{pid}'}
    transacoes = {'101': dados(101)}
    def api(url, **kwargs):
        r = Mock(status_code=200)
        r.json.return_value = transacoes[url.rsplit('/',1)[-1]]
        return r
    get.side_effect = api
    return pid, dados, transacoes, None


def confirmar(ambiente, tx):
    return ambiente[1].post('/pagamentos/confirmar',json={'payment_id':str(tx),'curso_id':1})


def notificar(ambiente):
    if hasattr(m.Pagamento, 'checkout_identidade'):
        from test_webhook_mercadopago import notificar as atual
        return atual(ambiente)
    return ambiente[1].post('/webhooks/mercadopago?data.id=101',json={'type':'payment','data':{'id':'101'}})
