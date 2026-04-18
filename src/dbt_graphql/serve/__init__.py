"""dbt-mdl GraphQL API server.

Provides FastAPI + Ariadne GraphQL server backed by SQLAlchemy async.
Requires the ``api`` extra: ``pip install dbt-mdl[api]``
"""


def __getattr__(name):
    if name in ("create_app", "serve"):
        from . import app

        return getattr(app, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
