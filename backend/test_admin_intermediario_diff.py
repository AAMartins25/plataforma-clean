"""Verifica estruturalmente que alterações independentes não entraram no patch."""
import ast
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[1]
BASE='cdba603e9a8d3a3a04a77fc03863ad41c93c1a93'
def original(f):return subprocess.check_output(['git','show',BASE+':'+f],cwd=ROOT,text=True)
def estruturas(s,t):return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(s).body if isinstance(n,t)}

def test_funcoes_publicadas_preservadas():
    f='backend/app/main.py';b=estruturas(original(f),ast.FunctionDef);a=estruturas((ROOT/f).read_text(),ast.FunctionDef)
    assert set(a)-set(b)=={'exigir_admin_intermediario'} and not set(b)-set(a)
    assert {n for n in b if b[n]!=a[n]}=={'criar_curso','criar_disciplina','associar_disciplina_ao_curso','criar_assunto','me','admin_criar_aluno'}

def test_modelos_schemas_preservados():
    for f,alterada,nova in [('backend/app/models.py','Usuario',{'AuditoriaPerfilAdmin'}),('backend/app/schemas.py','UsuarioResponse',set())]:
        b=estruturas(original(f),ast.ClassDef);a=estruturas((ROOT/f).read_text(),ast.ClassDef)
        assert set(a)-set(b)==nova and not set(b)-set(a)
        assert {n for n in b if b[n]!=a[n]}=={alterada}

def test_modulos_independentes_identicos():
    files=['backend/app/auth.py','backend/app/database.py','backend/app/transacoes_mp.py','backend/app/checkout_seguro.py',
      'backend/app/direitos_acesso.py','backend/app/contestacoes.py','backend/app/pausa_financeira.py','backend/app/emails_pagamentos.py',
      'backend/app/cupons_admin.py','backend/app/desempenho.py','backend/app/revisoes.py','backend/app/juridico.py',
      'backend/manutencao_temporaria.py','site-html/js/app.js','site-html/js/login.js','site-html/js/perfis.js','site-html/js/admin-criar-curso-completo.js']
    for f in files:assert (ROOT/f).read_text()==original(f),f

def test_rotas_preservadas_sem_ativacao():
    def rotas(s):return {ast.dump(d,include_attributes=False) for n in ast.walk(ast.parse(s)) if isinstance(n,ast.FunctionDef)
        for d in n.decorator_list if isinstance(d,ast.Call) and isinstance(d.func,ast.Attribute) and d.func.attr in {'get','post','put','delete','patch'}}
    f='backend/app/main.py';assert rotas(original(f))==rotas((ROOT/f).read_text())
    s=(ROOT/'backend/app/admin_intermediario.py').read_text()
    assert 'os.getenv' not in s and 'os.environ' not in s
    assert not (ROOT/'backend/app/perfis_admin.py').exists()
