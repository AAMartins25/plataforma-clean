const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const http=require('node:http');

const raiz=__dirname;
const origem='http://127.0.0.1:18762';
const hostProducao='https://plataforma-quality-backend.onrender.com';

function ativos(diretorio=raiz){
 return fs.readdirSync(diretorio,{withFileTypes:true}).flatMap(item=>{
  const arquivo=path.join(diretorio,item.name);
  if(item.isDirectory())return ativos(arquivo);
  return /\.(html|js)$/.test(item.name)?[arquivo]:[];
 });
}

function obter(caminho){
 return new Promise((resolve,reject)=>http.get(origem+'/'+path.relative(raiz,caminho).split(path.sep).map(encodeURIComponent).join('/'),res=>{
  const partes=[];res.setEncoding('utf8');res.on('data',parte=>partes.push(parte));res.on('end',()=>resolve({status:res.statusCode,corpo:partes.join('')}));
 }).on('error',reject));
}

test('proxy serve HTML/JS do Codespace usando somente a API isolada',async()=>{
 const arquivos=ativos().filter(arquivo=>fs.readFileSync(arquivo,'utf8').includes(hostProducao));
 const respostas=[];
 for(const arquivo of arquivos)respostas.push(await obter(arquivo));
 assert.ok(respostas.length>0,'a varredura deve encontrar referências de API');
 assert.ok(respostas.every(r=>r.status===200),'todos os ativos devem ser servidos');
 assert.ok(respostas.every(r=>!r.corpo.includes(hostProducao)),'nenhum ativo servido pode apontar à produção');
 const teoria=await obter(path.join(raiz,'teoria.html'));
 assert.match(teoria.corpo,/const API_BASE = "\/api"/);
 const app=await obter(path.join(raiz,'js/app.js'));
 assert.match(app.corpo,/const API_BASE = "\/api"/);
 const api=await new Promise((resolve,reject)=>http.get(origem+'/api/openapi.json',res=>{
  res.resume();res.on('end',()=>resolve(res.statusCode));
 }).on('error',reject));
 assert.equal(api,200,'o proxy /api deve alcançar o backend isolado');
});
