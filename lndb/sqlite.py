from contextlib import contextmanager
from raddoo import first, values
import sqlite3


conn = None


def dict_factory(cursor, row):
    return {
        col[0]: row[i]
        for i, col in enumerate(cursor.description)
    }


def path(name):
    return f'data/{name}.db'


def uri(name, mode):
    return f'file:{path(name)}?mode={mode}'


@contextmanager
def connect(name, mode='rwc'):
    global conn

    conn = sqlite3.connect(path(name))
    conn.row_factory = dict_factory

    try:
        yield conn
    finally:
        conn.commit()
        conn.close()

        conn = None



def execute(q, args=[]):
    cur = conn.cursor()

    cur.execute(q, args)

    return cur


def all(q, args=[]):
    return execute(q, args).fetchall()


def col(q, args=[]):
    return (first(row.values()) for row in all(q, args))


def one(q, args=[]):
    return execute(q, args).fetchone()


def val(q, args=[]):
    return first(values(one(q, args) or {}))


# Migrate


with connect('master'):
    #  execute("DROP TABLE account")
    #  execute("DROP TABLE token")
    #  execute("DROP TABLE invoice")

    execute("""CREATE TABLE IF NOT EXISTS account
               (id text NOT NULL,
                balance int NOT NULL DEFAULT 0,
                parent text)""")

    execute("""CREATE TABLE IF NOT EXISTS token
               (id txt NOT NULL,
                value text NOT NULL,
                scope text NOT NULL,
                account text NOT NULL)""")

    execute("""CREATE TABLE IF NOT EXISTS invoice
               (hash text NOT NULL,
                account text NOT NULL,
                bolt11 text NOT NULL,
                expires integer NOT NULL,
                amount_msat integer NOT NULL,
                secret text NOT NULL,
                status text NOT NULL DEFAULT 'pending')""")


def ensure_resource(resource):
    execute(
        SQL(
            """CREATE TABLE IF NOT EXISTS {}
               (id bigserial PRIMARY KEY, instance jsonb NOT NULL)"""
        ).format(resource)
    )


def insert_resource(resource, instance):
    return val(
        SQL("INSERT INTO {} (instance) VALUES ({}) RETURING id").format(
            Identifier(resource),
            Literal(instance)
        )
    )
