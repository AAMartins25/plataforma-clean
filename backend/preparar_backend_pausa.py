"""Exporta versão intermediária sem alterar o checkout ou publicar código.

Uso: python backend/preparar_backend_pausa.py --destino /tmp/resumao-pausa-bootstrap
Extrai o backend da origem revisada, antes da implementação financeira definitiva.
"""
import argparse
import ast
import io
from pathlib import Path
import subprocess
import tarfile


def ajustar_checkout(s):
    inicio=s.index('def criar_checkout_mp(')
    node=next(n for n in ast.parse(s).body if isinstance(n,ast.FunctionDef) and n.name=='criar_checkout_mp')
    linhas=s.splitlines(keepends=True)
    fim=sum(len(l) for l in linhas[:node.end_lineno])
    trecho=s[inicio:fim]
    if 'CHECKOUT_INDEFINIDO' in trecho:
        return s
    anchor='    titulos_gerados = db.query(Pagamento).filter('
    if anchor not in trecho or '    try:\n        resp = requests.post(' not in trecho:
        raise ValueError('Checkout de origem incompatível com preparação transacional.')
    trecho=trecho.replace(anchor, """    indefinido = db.query(Pagamento).filter(
        Pagamento.oportunidade_id == oportunidade.id,
        Pagamento.status == 'CHECKOUT_INDEFINIDO',
        Pagamento.mp_preference_id.is_(None)
    ).first()
    if indefinido:
        from app.financeiro_transacional import esperar_checkout
        if esperar_checkout(db, indefinido.id):
            return criar_checkout_mp(payload, db, user)
        raise HTTPException(409, 'A abertura anterior do checkout precisa ser verificada no provedor antes de outra tentativa.')

"""+anchor)
    trecho=trecho.replace("            'PENDENTE',", "            'CHECKOUT_INDEFINIDO',",1)
    trecho=trecho.replace('    try:\n        resp = requests.post(', """    # Identidade durável antes do efeito externo; não confirma pagamento ou acesso.
    db.commit()
    # Preservar a serialização comercial; revalidar modo/geração após o commit.
    db.query(models.Usuario).filter(models.Usuario.id == user.id).with_for_update().one()

    try:
        resp = requests.post(""",1)
    trecho=trecho.replace('SET mp_preference_id = :pid', "SET mp_preference_id = :pid, status = 'PENDENTE'",1)
    return s[:inicio]+trecho+s[fim:]


def preparar(destino, origem='HEAD'):
    raiz = Path(__file__).resolve().parents[1]
    destino = Path(destino).resolve()
    if destino.exists():
        raise ValueError('Destino deve ser novo; nenhum arquivo existente será sobrescrito.')
    sha = subprocess.check_output(['git','rev-parse','--verify',origem+'^{commit}'],cwd=raiz,text=True).strip()
    dados = subprocess.check_output(['git','archive',sha,'backend'],cwd=raiz)
    destino.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(dados)) as arquivo:
        arquivo.extractall(destino, filter='data')
    backend = destino/'backend'
    modelos=(backend/'app/models.py').read_text()
    if 'pagamento_origem_id' in modelos or 'mp_status' in modelos:
        raise ValueError('HEAD já contém a lógica definitiva; interromper e selecionar a origem anterior revisada.')
    source = raiz/'backend'
    for nome in ('pausa_financeira.py', 'financeiro_transacional.py', 'database.py', 'contratacoes.py', 'oportunidades.py'):
        (backend/'app'/nome).write_bytes((source/'app'/nome).read_bytes())
    for nome in ('016_pausa_financeira_webhooks.sql','016_pausa_financeira_webhooks.md'):
        (backend/'migrations'/nome).write_bytes((source/'migrations'/nome).read_bytes())
    main = backend/'app/main.py'
    s = main.read_text()
    start = s.index('async def webhook_mercadopago(')
    pos = s.index('    r = requests.get(',start)
    s = s[:pos]+'    from starlette.concurrency import run_in_threadpool\n    return await run_in_threadpool(processar_pagamento_mp, str(payment_id), db)\n\n\ndef processar_pagamento_mp(payment_id, db, resposta_mp=None):\n'+s[pos:]
    pos=s.index('    r = requests.get(',s.index('def processar_pagamento_mp('))
    s=s[:pos]+s[pos:].replace('    r = requests.get(', '    r = resposta_mp if resposta_mp is not None else requests.get(',1)
    # Preservar assinatura e proteger também chamadas diretas ao backend antigo.
    s='from app.financeiro_transacional import protegido\n'+s
    for nome in ('admin_criar_acesso','iniciar_demonstracao_curso','criar_checkout_mp',
                 'confirmar_pagamento','processar_pagamento_mp','admin_revalidar_pagamento',
                 'solicitar_reembolso','aprovar_reembolso','recusar_reembolso',
                 'registrar_reembolso_pix_manual','confirmar_reembolso_pix_manual',
                 'recalcular_acesso_apos_reembolso'):
        s=s.replace('def '+nome+'(', '@protegido\ndef '+nome+'(')
    s+='\n\nfrom app.pausa_financeira import instalar\nfrom app.database import engine as motor_financeiro\ninstalar(app, motor_financeiro, SessionLocal, get_db, get_usuario_atual,\n    validar_assinatura_mercadopago, processar_pagamento_mp, mp_headers, definitivo=False,\n    consulta=lambda pid: requests.get(f\"https://api.mercadopago.com/v1/payments/{pid}\", headers=mp_headers(), timeout=20))\n'
    s=ajustar_checkout(s)
    ast.parse(s)
    main.write_text(s)
    (destino/'ORIGEM.txt').write_text(f'Backend intermediário baseado em {sha}\nSem lógica 014/015. Exportação local; não publicada.\n')
    return sha


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destino',required=True)
    parser.add_argument('--origem',default='HEAD',help='SHA/ref da versão anterior revisada (padrão HEAD).')
    args=parser.parse_args()
    print('Exportação local concluída. Origem:', preparar(args.destino, args.origem))
