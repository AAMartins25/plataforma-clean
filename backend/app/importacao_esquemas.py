"""Contrato versionado para importação; componentes reutilizáveis em importações futuras."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from app.schemas import CursoMetadados


class Estrito(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

    @field_validator('*', mode='after')
    @classmethod
    def texto_nao_vazio(cls, valor):
        if isinstance(valor, str) and not valor.strip():
            raise ValueError('O campo não pode estar vazio')
        return valor


class CursoImportado(CursoMetadados):
    model_config = ConfigDict(extra='forbid', strict=True)
    nome: str = Field(min_length=1, max_length=255)
    banca: str = Field(min_length=1, max_length=255)
    cargo: str = Field(min_length=1, max_length=255)
    orgao: str = Field(min_length=1, max_length=255)
    ano: int = Field(ge=1000, le=9999)
    uf: str
    descricao_publica_markdown: str = Field(min_length=1, max_length=250000)

    @field_validator('nome', 'descricao_publica_markdown')
    @classmethod
    def descricao_nao_vazia(cls, valor):
        if not valor.strip():
            raise ValueError('A descrição não pode estar vazia')
        return valor


class ResumoImportado(Estrito):
    titulo: str = Field(min_length=1, max_length=255)
    texto_markdown: str = Field(min_length=1, max_length=250000)


class QuestaoImportada(Estrito):
    tipo: Literal['MULTIPLA_4', 'MULTIPLA_5', 'CERTO_ERRADO']
    enunciado_markdown: str = Field(min_length=1, max_length=250000)
    alternativas: dict[str, str]
    gabarito: str
    comentario_markdown: str = Field(min_length=1, max_length=250000)

    @model_validator(mode='after')
    def alternativas_validas(self):
        letras = {'MULTIPLA_4': 'ABCD', 'MULTIPLA_5': 'ABCDE', 'CERTO_ERRADO': ''}[self.tipo]
        if set(self.alternativas) != set(letras):
            raise ValueError('Alternativas incompatíveis com o tipo da questão')
        if any(not texto.strip() or len(texto) > 250000 for texto in self.alternativas.values()):
            raise ValueError('Alternativa vazia ou maior que 250.000 caracteres')
        if self.gabarito not in (letras if letras else 'CE'):
            raise ValueError('Gabarito incompatível com o tipo da questão')
        return self


class BateriaImportada(Estrito):
    titulo: str = Field(min_length=1, max_length=255)
    tipo: Literal['MULTIPLA', 'CERTO_ERRADO']
    questoes: list[QuestaoImportada] = Field(min_length=10, max_length=10)

    @model_validator(mode='after')
    def familia_questoes(self):
        if any((q.tipo == 'CERTO_ERRADO') != (self.tipo == 'CERTO_ERRADO') for q in self.questoes):
            raise ValueError('Não misture múltipla escolha e certo/errado na mesma bateria')
        return self


class AssuntoImportado(Estrito):
    nome: str = Field(min_length=1, max_length=255)
    aula_titulo: str = Field(min_length=1, max_length=255)
    resumos: list[ResumoImportado] = Field(max_length=20)
    baterias: list[BateriaImportada] = Field(max_length=20)


class DisciplinaImportada(Estrito):
    nome: str = Field(min_length=1, max_length=255)
    assuntos: list[AssuntoImportado]


class ImportacaoCursoV1(Estrito):
    versao: Literal[1]

    @field_validator('versao', mode='before')
    @classmethod
    def versao_inteira(cls, valor):
        if type(valor) is not int or valor != 1:
            raise ValueError('A versão deve ser o inteiro 1')
        return valor

    curso: CursoImportado
    disciplinas: list[DisciplinaImportada]
