"""Camada semantica: uma funcao por metrica, um modulo por dominio.

Contrato de todo modulo daqui:

* assinatura tipada, primeiro argumento sempre ``filtros: Filtros``
  (ou ``data_ref`` quando a metrica e uma foto);
* docstring com a **definicao de negocio** e a **armadilha tratada**;
* retorno sempre ``pandas.DataFrame`` pronto para plotar, com nomes de coluna
  estaveis (o front-end depende deles);
* SQL sempre parametrizado, sempre via :func:`frotas.db.consultar`.
"""

from frotas.metrics import alertas, credito, custos, dimensoes, metas, receita

__all__ = ["receita", "credito", "custos", "metas", "dimensoes", "alertas"]
