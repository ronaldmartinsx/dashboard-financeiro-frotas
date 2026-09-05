"""Pacote do data app de frotas: acesso a dados + camada semantica.

Camadas (detalhe em ``docs/02_arquitetura.md``)::

    views/  ->  frotas.metrics.*  ->  frotas.db.consultar  ->  Supabase (read-only)
                      ^
                      |
                frotas.filtros.Filtros

O front-end consome exclusivamente ``frotas.metrics`` e ``frotas.filtros``; nao
escreve SQL nem toca em ``frotas.db`` diretamente.
"""

__all__ = ["config", "db", "filtros", "metrics"]
