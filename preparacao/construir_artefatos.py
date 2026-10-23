"""Empacota somente base publicada + mudanças locais explicitamente aprovadas."""
import difflib
import gzip
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile

ROOT=Path(__file__).resolve().parents[1]
BASE='cdba603e9a8d3a3a04a77fc03863ad41c93c1a93'


def construir():
    baseline={};modes={}
    raw=subprocess.check_output(['git','archive',BASE],cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        for m in archive.getmembers():
            if m.isdir():continue
            if not m.isfile():raise ValueError('Base contém entrada não regular')
            baseline[m.name]=archive.extractfile(m).read();modes[m.name]=m.mode
    approved=json.loads((ROOT/'evidencias/manifesto.json').read_text())
    for f,h in approved['arquivos'].items():
        if hashlib.sha256((ROOT/f).read_bytes()).hexdigest()!=h:
            raise ValueError('Arquivo do patch auditado mudou: '+f)
    assets=list((ROOT/'site-html/js').glob('admin-intermediario-022.*.js'))
    if len(assets)!=1:raise ValueError('Esperado um asset administrativo versionado')
    asset=assets[0];digest=hashlib.sha256((ROOT/'site-html/js/admin.js').read_bytes()).hexdigest()
    if asset.name!='admin-intermediario-022.'+digest[:16]+'.js' or asset.read_bytes()!=(ROOT/'site-html/js/admin.js').read_bytes():
        raise ValueError('Asset e hash não correspondem ao admin.js auditado')
    front={'site-html/js/admin.js':(ROOT/'site-html/js/admin.js').read_bytes(),
           asset.relative_to(ROOT).as_posix():asset.read_bytes()}
    pages=[]
    for p in sorted((ROOT/'site-html/admin').glob('*.html')):
        f=p.relative_to(ROOT).as_posix();data=p.read_bytes()
        if b'src="../js/admin.js"' not in baseline[f]:
            if data!=baseline[f]:raise ValueError('HTML fora do escopo mudou: '+f)
            continue
        if data.replace(asset.name.encode(),b'admin.js')!=baseline[f]:
            raise ValueError('HTML contém alteração fora do versionamento: '+f)
        if asset.name.encode() not in data:raise ValueError('HTML sem asset versionado: '+f)
        front[f]=data;pages.append(f)
    if len(pages)!=18:raise ValueError('Inventário administrativo mudou; revisar')
    full=dict(baseline)
    for f in approved['arquivos']:full[f]=(ROOT/f).read_bytes()
    full.update(front)
    frontend={f:b for f,b in baseline.items() if f.startswith('site-html/')};frontend.update(front)
    timestamp=int(subprocess.check_output(['git','show','-s','--format=%ct',BASE],cwd=ROOT,text=True))
    out=ROOT/'artefatos';out.mkdir(exist_ok=True)
    def pacote(name,files,kind,uses):
        hashes={f:hashlib.sha256(b).hexdigest() for f,b in sorted(files.items())}
        tree=hashlib.sha256(json.dumps(hashes,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        manifest={'base_sha':BASE,'release_id':kind+'-'+tree[:16],'kind':kind,
          'allowed_uses':uses,'restritos_habilitados':False,'source_tree_sha256':tree,'files':hashes}
        entries={**files,'RELEASE-MANIFEST.json':(json.dumps(manifest,sort_keys=True,indent=2)+'\n').encode()}
        buf=io.BytesIO()
        with gzip.GzipFile(fileobj=buf,mode='wb',filename='',mtime=0) as gz:
            with tarfile.open(fileobj=gz,mode='w',format=tarfile.PAX_FORMAT) as archive:
                for f,data in sorted(entries.items()):
                    if Path(f).name=='.env' or '.git' in Path(f).parts:raise ValueError('Arquivo não permitido')
                    info=tarfile.TarInfo(f);info.size=len(data);info.mode=modes.get(f,0o644);info.mtime=timestamp
                    archive.addfile(info,io.BytesIO(data))
        data=buf.getvalue();(out/name).write_bytes(data)
        return {'sha256':hashlib.sha256(data).hexdigest(),'release_id':manifest['release_id'],
                'allowed_uses':uses,'arquivos':len(files)}
    index={'base_sha':BASE,'asset':asset.name,'pacotes':{}}
    index['pacotes']['frontend-compativel.tar.gz']=pacote('frontend-compativel.tar.gz',frontend,'frontend-compativel',['frontend'])
    index['pacotes']['backend-intermediario.tar.gz']=pacote('backend-intermediario.tar.gz',full,'intermediario-seguro',['backend','recuperacao'])
    (out/'recuperacao-intermediario.tar.gz').write_bytes((out/'backend-intermediario.tar.gz').read_bytes())
    index['pacotes']['recuperacao-intermediario.tar.gz']=dict(index['pacotes']['backend-intermediario.tar.gz'])
    def patch_local(entries):
        lines=[]
        for f,data in sorted(entries.items()):
            if baseline.get(f)==data:continue
            old=baseline.get(f,b'').decode();new=data.decode()
            lines.append('diff --git a/'+f+' b/'+f+'\n')
            if f not in baseline:lines.append('new file mode 100644\n')
            for line in difflib.unified_diff(old.splitlines(True),new.splitlines(True),
                fromfile='a/'+f if f in baseline else '/dev/null',tofile='b/'+f):
                lines.append(line if line.endswith('\n') else line+'\n\\ No newline at end of file\n')
        return ''.join(lines)
    (out/'frontend-primeiro.patch').write_text(patch_local(front))
    (out/'intermediario-completo.patch').write_text(patch_local(full))
    (out/'verificar_artefato.py').write_bytes((ROOT/'preparacao/verificar_artefato.py').read_bytes())
    import importlib.metadata
    import platform
    import re
    import sys
    names=[re.split(r'[\[<>=!~ ]',line.strip())[0] for line in (ROOT/'backend/requirements.txt').read_text().splitlines() if line.strip() and not line.startswith('#')]
    names.append('psycopg-binary')
    deps={}
    for name in names:
        try:deps[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:deps[name]='não instalado neste ambiente'
    (out/'DEPENDENCIAS-TESTADAS.json').write_text(json.dumps({'python':sys.version.split()[0],
        'plataforma':platform.system()+'/'+platform.machine(),'versoes_locais':deps,
        'observacao':'Registro local; não é lock ou imagem do runtime Render.'},indent=2,ensure_ascii=False)+'\n')
    index['patches']={name:hashlib.sha256((out/name).read_bytes()).hexdigest() for name in ['frontend-primeiro.patch','intermediario-completo.patch']}
    index['verificador_sha256']=hashlib.sha256((out/'verificar_artefato.py').read_bytes()).hexdigest()
    (out/'INDICE.json').write_text(json.dumps(index,indent=2,ensure_ascii=False)+'\n')
    checks={name:p['sha256'] for name,p in index['pacotes'].items()}
    for name in ['frontend-primeiro.patch','intermediario-completo.patch','verificar_artefato.py','DEPENDENCIAS-TESTADAS.json','INDICE.json']:
        checks[name]=hashlib.sha256((out/name).read_bytes()).hexdigest()
    (out/'SHA256SUMS').write_text(''.join(digest+'  '+name+'\n' for name,digest in checks.items()))
    return index

if __name__=='__main__':print(json.dumps(construir(),indent=2,ensure_ascii=False))
