from contextlib import contextmanager
from raddoo import first, values, env
from psycopg2 import connect
from psycopg2.sql import SQL, Identifier, Literal
from psycopg2.extras import RealDictCursor, RealDictRow


class MyCursor(RealDictCursor):
    def all(self, q, args=[]):
        self.execute(q, args)

        return self.fetchall()


    def col(self, q, args=[]):
        return (first(row.values()) for row in self.all(q, args))


    def one(self, q, args=[]):
        self.execute(q, args)

        return self.fetchone()


    def val(self, q, args=[]):
        return first(values(self(q, args) or {}))


conn = connect(env('DATABASE_URL'), cursor_factory=MyCursor)
conn.autocommit = True


@contextmanager
def cursor(schema):
    global conn

    with conn.cursor() as cur:
        cur.execute("set search_path to {}", (schema,))

        try:
            yield cur
        finally:
            cur.execute("set search_path to bogus")


# Migrate


#  execute("DROP TABLE account")
#  execute("DROP TABLE token")
#  execute("DROP TABLE invoice")

with search_path('master') as cur:
    execute("""
    CREATE SCHEMA IF NOT EXISTS ;
    CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

    CREATE TABLE IF NOT EXISTS account
       (id uuid NOT NULL,
        balance int NOT NULL DEFAULT 0,
        parent uuid);

    CREATE TABLE IF NOT EXISTS token
       (id uuid NOT NULL,
        value text NOT NULL,
        scope text NOT NULL,
        account uuid NOT NULL);

    CREATE TABLE IF NOT EXISTS invoice
       (hash text NOT NULL,
        account uuid NOT NULL,
        bolt11 text NOT NULL,
        expires integer NOT NULL,
        amount_msat integer NOT NULL,
        secret text NOT NULL,
        status text NOT NULL DEFAULT 'pending');

    ALTER TABLE token ADD CONSTRAINT fk_account (account)
        REFERENCES account(id) DEFERRABLE;

    ALTER TABLE invoice ADD CONSTRAINT fk_account (account)
        REFERENCES account(id) DEFERRABLE;
    """)


# Resource helpers


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
