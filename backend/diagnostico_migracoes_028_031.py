#!/usr/bin/env python3
"""Diagnóstico somente de leitura; conexão exclusivamente via serviço libpq.

Requer PGSERVICE configurado fora do repositório e autenticação privada libpq.
Não lê DATABASE_URL, dotenv, argumentos de conexão ou arquivos do aplicativo.
"""
import json
import os
import re
import sys

try:
    import psycopg
    from psycopg import sql
except ImportError:
    print('INCONCLUSIVO: dependência psycopg ausente.')
    sys.exit(2)


def executar():
    if len(sys.argv) != 1 or not os.environ.get('PGSERVICE'):
        print('INCONCLUSIVO: informe somente PGSERVICE por configuração privada libpq.')
        return 2
    if os.environ.get('PGOPTIONS'):
        print('INCONCLUSIVO: remova PGOPTIONS para evitar alterações de sessão externas.')
        return 2
    relatorio = {'resultado': 'INCONCLUSIVO', 'identidade': {}, 'historico': {},
                 'estrutura': {}, 'contagens': {}, 'justificativas': []}
    erros, pendencias = [], []
    # Libpq consulta PGSERVICE/PGPASSFILE sem colocar senha nos argumentos.
    try:
        with psycopg.connect('', connect_timeout=5, autocommit=True) as conn:
            with conn.transaction():
                conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
                conn.execute("SET LOCAL lock_timeout = '5s'")
                conn.execute("SET LOCAL statement_timeout = '30s'")
                conn.execute("SET LOCAL idle_in_transaction_session_timeout = '60s'")
                conn.execute("SET LOCAL search_path = pg_catalog")
                # Não aceitar contagem parcial devido a RLS: consulta falhará se aplicável.
                conn.execute('SET LOCAL row_security = off')
                db, versao, papel = conn.execute(
                    "SELECT current_database(), current_setting('server_version'), current_user").fetchone()
                relatorio['identidade'] = {'banco': db, 'esquema_alvo': 'public',
                                           'postgresql': versao, 'papel_diagnostico': papel}
                if conn.execute("SELECT current_setting('transaction_read_only')").fetchone()[0] != 'on':
                    raise RuntimeError('transação não é somente leitura')
                if int(conn.execute("SELECT current_setting('server_version_num')").fetchone()[0]) < 140000:
                    erros.append('PostgreSQL anterior à versão 14, exigida pelas proteções financeiras existentes.')
                if conn.execute("SELECT to_regprocedure('pg_catalog.hashtextextended(text,bigint)') IS NOT NULL").fetchone()[0] is False:
                    erros.append('Função hashtextextended necessária aos bloqueios de concorrência está ausente.')

                schema = conn.execute("SELECT to_regnamespace('public') IS NOT NULL").fetchone()[0]
                if not schema:
                    erros.append('Esquema public ausente.')
                else:
                    # current_user precisa ser o papel previsto para executar as migrações;
                    # permissões alheias não são inferidas.
                    uso, criar = conn.execute("SELECT has_schema_privilege(current_user,'public','USAGE'), "
                                               "has_schema_privilege(current_user,'public','CREATE')").fetchone()
                    if not uso or not criar:
                        pendencias.append('Papel atual não demonstra USAGE e CREATE no esquema public; conferir papel executor.')

                tabelas = ['usuarios', 'cursos', 'tempo_acesso_curso', 'contratacoes_curso',
                           'acessos_curso', 'importacoes_curso', 'operacoes_acesso_admin']
                dados = {}
                for nome in tabelas:
                    row = conn.execute("""SELECT c.oid, c.relkind, c.relrowsecurity,
                        c.relforcerowsecurity, pg_has_role(current_user,c.relowner,'USAGE')
                        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                        WHERE n.nspname='public' AND c.relname=%s""", (nome,)).fetchone()
                    dados[nome] = row
                    relatorio['estrutura'][nome] = 'ausente' if not row else ('tabela' if row[1] in ('r','p') else 'objeto incompatível')
                    if row and row[1] not in ('r','p'):
                        erros.append(f'public.{nome} existe mas não é tabela.')
                for nome in tabelas[:5]:
                    if not dados[nome]:
                        erros.append(f'Tabela necessária public.{nome} ausente.')

                colunas = {}
                for nome, row in dados.items():
                    if not row or row[1] not in ('r','p'):
                        continue
                    colunas[nome] = {r[0]: (r[1], r[2], r[3]) for r in conn.execute("""
                        SELECT a.attname, format_type(a.atttypid,a.atttypmod), a.attnotnull,
                               pg_get_expr(d.adbin,d.adrelid)
                        FROM pg_attribute a LEFT JOIN pg_attrdef d
                          ON d.adrelid=a.attrelid AND d.adnum=a.attnum
                        WHERE a.attrelid=%s AND a.attnum>0 AND NOT a.attisdropped""", (row[0],))}

                necessarias = {'usuarios': {'id':'integer'}, 'cursos': {'id':'integer'},
                    'tempo_acesso_curso': {'curso_id':'integer','meses':'integer','valor_cents':'integer'},
                    'contratacoes_curso': {'id':'integer'}, 'acessos_curso': {'id':'integer'}}
                for tabela, campos in necessarias.items():
                    if tabela not in colunas: continue
                    for campo, tipo in campos.items():
                        if campo not in colunas[tabela] or colunas[tabela][campo][0] != tipo:
                            erros.append(f'Coluna public.{tabela}.{campo} ausente ou tipo incompatível (esperado {tipo}).')

                # A referência exige índice único válido de uma coluna, imediato e não parcial.
                for nome in ('usuarios','cursos','contratacoes_curso','acessos_curso'):
                    if nome not in colunas or 'id' not in colunas[nome]: continue
                    valido = conn.execute("""SELECT EXISTS (
                        SELECT FROM pg_index i JOIN pg_attribute a ON a.attrelid=i.indrelid
                        WHERE i.indrelid=%s AND a.attname='id' AND i.indisunique
                          AND i.indisvalid AND i.indisready AND i.indimmediate
                          AND i.indpred IS NULL AND i.indexprs IS NULL
                          AND i.indnkeyatts=1 AND i.indkey[0]=a.attnum)""", (dados[nome][0],)).fetchone()[0]
                    if not valido:
                        erros.append(f'public.{nome}.id não possui índice único compatível com chave estrangeira.')
                    if not conn.execute("SELECT has_column_privilege(current_user,%s,'id','REFERENCES')", (dados[nome][0],)).fetchone()[0]:
                        pendencias.append(f'Papel atual não demonstra REFERENCES em public.{nome}.id.')

                for nome in ('cursos','tempo_acesso_curso'):
                    if not dados[nome] or dados[nome][1] not in ('r','p'): continue
                    oid, _, _, _, owner = dados[nome]
                    if not owner:
                        pendencias.append(f'Papel atual não demonstra propriedade necessária para ALTER TABLE public.{nome}.')
                    for privilegio in ('SELECT','UPDATE'):
                        if not conn.execute('SELECT has_table_privilege(current_user,%s,%s)', (oid,privilegio)).fetchone()[0]:
                            pendencias.append(f'Papel atual não demonstra {privilegio} em public.{nome}.')

                esperadas = {
                    ('cursos','precos_provisorios'): ('boolean',True,'false'),
                    ('cursos','demonstracao_por_ordem'): ('boolean',True,'false'),
                    ('tempo_acesso_curso','valor_provisorio_original_cents'): ('integer',False,None)}
                encontrados = []
                for (tabela,campo), esperado in esperadas.items():
                    valor=colunas.get(tabela,{}).get(campo)
                    relatorio['estrutura'][f'{tabela}.{campo}'] = 'presente' if valor else 'ausente'
                    if valor:
                        encontrados.append(f'{tabela}.{campo}')
                        tipo,notnull,default=valor
                        # pg_get_expr normalmente retorna false; aceitar parênteses triviais.
                        norm = default.strip(' ()').lower() if default is not None else None
                        if (tipo,notnull,norm) != esperado:
                            erros.append(f'public.{tabela}.{campo} tem definição incompatível.')

                novos = {
                  'importacoes_curso': {'chave':('character varying(64)',True), 'hash_requisicao':('character varying(64)',True),
                    'usuario_id':('integer',True),'curso_id':('integer',True),'criado_em':('timestamp without time zone',True)},
                  'operacoes_acesso_admin': {'chave':('character varying(64)',True),'administrador_id':('integer',True),
                    'hash_requisicao':('character varying(64)',True),'contratacao_id':('integer',True),
                    'acesso_id':('integer',True),'criada_em':('timestamp without time zone',True)}}
                fks={'importacoes_curso':{'usuario_id':'usuarios','curso_id':'cursos'},
                     'operacoes_acesso_admin':{'administrador_id':'usuarios','contratacao_id':'contratacoes_curso','acesso_id':'acessos_curso'}}
                for tabela, campos in novos.items():
                    if tabela not in colunas: continue
                    encontrados.append(tabela)
                    for campo,(tipo,nn) in campos.items():
                        valor=colunas[tabela].get(campo)
                        if not valor or valor[:2]!=(tipo,nn):
                            erros.append(f'public.{tabela}.{campo} ausente ou incompatível.')
                    criado='criado_em' if tabela=='importacoes_curso' else 'criada_em'
                    criado_def=colunas[tabela].get(criado)
                    if criado_def and (criado_def[2] or '').strip().lower() not in ('now()', 'current_timestamp'):
                        erros.append(f'public.{tabela}.{criado}: padrão de criação ausente ou incompatível.')
                    constraints=conn.execute("""SELECT c.contype, a.attname, rn.nspname, rt.relname, ra.attname,
                            c.convalidated, c.condeferrable
                        FROM pg_constraint c
                        LEFT JOIN pg_attribute a ON a.attrelid=c.conrelid AND a.attnum=c.conkey[1]
                        LEFT JOIN pg_class rt ON rt.oid=c.confrelid
                        LEFT JOIN pg_namespace rn ON rn.oid=rt.relnamespace
                        LEFT JOIN pg_attribute ra ON ra.attrelid=c.confrelid AND ra.attnum=c.confkey[1]
                        WHERE c.conrelid=%s AND cardinality(c.conkey)=1""",(dados[tabela][0],)).fetchall()
                    if not any(c[0]=='p' and c[1]=='chave' and c[5] and not c[6] for c in constraints):
                        erros.append(f'public.{tabela}: chave primária imediata em chave ausente.')
                    indice_pk=conn.execute("""SELECT EXISTS(SELECT FROM pg_constraint c JOIN pg_index i ON i.indexrelid=c.conindid
                        WHERE c.conrelid=%s AND c.contype='p' AND i.indisvalid AND i.indisready AND i.indimmediate)""",(dados[tabela][0],)).fetchone()[0]
                    if not indice_pk:
                        erros.append(f'public.{tabela}: índice da chave primária não está válido e pronto.')
                    for campo,destino in fks[tabela].items():
                        if not any(c[:5]==('f',campo,'public',destino,'id') and c[5] for c in constraints):
                            erros.append(f'public.{tabela}.{campo}: chave estrangeira validada ausente.')
                    if not conn.execute('SELECT has_table_privilege(current_user,%s,%s)',(dados[tabela][0],'SELECT')).fetchone()[0]:
                        pendencias.append(f'Papel atual não possui SELECT em public.{tabela}; contagem indisponível.')

                # Não assume que um registro direto de importação identifique suas cópias.
                if 'cursos' in colunas and 'precos_provisorios' in colunas['cursos'] and colunas['cursos']['precos_provisorios'][0]=='boolean':
                    relatorio['contagens']['cursos_provisorios'] = conn.execute('SELECT count(*) FROM public.cursos WHERE precos_provisorios IS TRUE').fetchone()[0]
                if 'importacoes_curso' in colunas:
                    relatorio['contagens']['importacoes_diretas'] = conn.execute('SELECT count(*) FROM public.importacoes_curso').fetchone()[0]
                if encontrados:
                    pendencias.append('Objetos 028–031 já existem: revisar estado parcial, definição e reconciliação antes de executar.')
                if dados['operacoes_acesso_admin']:
                    erros.append('Migração 031 integral falhará: public.operacoes_acesso_admin já existe.')
                if relatorio['contagens'].get('importacoes_diretas',0):
                    pendencias.append('Há importações diretas; eventuais cópias não são identificadas nem classificadas por este diagnóstico.')

                # Apenas nomes/versões conhecidas; nenhum conteúdo arbitrário ou dado pessoal.
                for tabela,campo in [('alembic_version','version_num'),('schema_migrations','version')]:
                    registro=conn.execute("""SELECT c.oid,c.relkind FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                        WHERE n.nspname='public' AND c.relname=%s""",(tabela,)).fetchone()
                    if not registro:
                        relatorio['historico'][tabela]='ausente'
                        continue
                    if registro[1] not in ('r','p') or not conn.execute("SELECT EXISTS(SELECT FROM pg_attribute WHERE attrelid=%s AND attname=%s AND attnum>0 AND NOT attisdropped)",(registro[0],campo)).fetchone()[0]:
                        relatorio['historico'][tabela]='estrutura não reconhecida'
                        pendencias.append(f'Histórico public.{tabela} requer revisão manual.')
                        continue
                    if not conn.execute('SELECT has_table_privilege(current_user,%s,%s)',(registro[0],'SELECT')).fetchone()[0]:
                        relatorio['historico'][tabela]='sem permissão de leitura'
                        pendencias.append(f'Sem leitura do histórico public.{tabela}.')
                        continue
                    q=sql.SQL('SELECT {}::text FROM public.{} ORDER BY 1 LIMIT 101').format(sql.Identifier(campo),sql.Identifier(tabela))
                    versoes=[r[0] for r in conn.execute(q)]
                    if len(versoes)>100:
                        relatorio['historico'][tabela]='conteúdo ou volume requer revisão manual'
                        pendencias.append(f'Histórico public.{tabela} não pode ser apresentado com segurança.')
                    else:
                        # Publicar apenas códigos conhecidos, nunca texto arbitrário de tabela de histórico.
                        codigos=[]
                        for v in versoes:
                            match=re.fullmatch(r'(0[0-2][0-9]|03[01])(?:_[A-Za-z_]{1,60})?',v) if isinstance(v,str) else None
                            if match: codigos.append(match.group(1))
                        relatorio['historico'][tabela]={'registros_examinados':len(versoes),
                            'codigos_reconhecidos':sorted(set(codigos)),
                            'registros_nao_reconhecidos':len(versoes)-len(codigos)}
                        if len(codigos)!=len(versoes):
                            pendencias.append(f'Histórico public.{tabela} contém revisões sem correspondência verificável; revisar sem exportar dados.')
                        if any(c in {'028','029','030','031'} for c in codigos):
                            pendencias.append(f'Histórico public.{tabela} registra migração 028–031; conciliar com os objetos antes de executar.')
                if all(v=='ausente' for v in relatorio['historico'].values()):
                    pendencias.append('Histórico de migrações não identificado nas tabelas reconhecidas; conferir registros externos.')
                relatorio['justificativas']=erros+pendencias
                relatorio['resultado']='NÃO APTO' if erros else 'INCONCLUSIVO' if pendencias else 'APTO'
    except Exception:
        # Não imprimir exceções de driver: podem conter DSN, host, usuário ou detalhes SQL.
        relatorio['resultado']='INCONCLUSIVO'
        relatorio['justificativas'].append('Não foi possível completar o diagnóstico somente de leitura; conferir conexão, permissões, RLS e limites sem expor credenciais.')
    print(json.dumps(relatorio,ensure_ascii=False,indent=2))
    return {'APTO':0,'NÃO APTO':1,'INCONCLUSIVO':2}[relatorio['resultado']]


if __name__ == '__main__':
    sys.exit(executar())
