import sqlite3, os, functools, math, time, json
from raddoo import last, random_uuid, env, prop
from dotenv import load_dotenv
from flask import Flask, request, g
from flask_restful import Resource, Api
from flasgger import Swagger
from secrets import token_hex
from lndb import sqlite, pg, ibex

load_dotenv()

app = Flask(__name__)
api = Api(app)
swag = Swagger(app)


all_scopes = {'all', 'all/readonly', 'account/create'}


@app.after_request
def after_request(res):
    if getattr(g, 'account', None):
        res.headers.add('X-Lndb-Account-Balance', g.account['balance'])

    return res


def err(code, message):
    return {'code': code, 'error': message}


def provide_auth():
    def dec(f):
        @functools.wraps(f)
        def wrapper(*args, **kw):
            auth = request.headers.get('Authorization', '')
            token = last(auth.lower().split('bearer')).strip()

            with pg.connect('master'):
                g.token = pg.one("SELECT * FROM token WHERE value = %s", [token])

                # If they provided a token, but it wasn't valid, don't treat them
                # as anonymous, fail fast instead
                if auth and not g.token:
                    return err('forbidden', 'Forbidden'), 401

                if g.token:
                    g.account = pg.one(
                        "SELECT * FROM account WHERE id = %s",
                        [g.token['account']]
                    )

            return f(*args, **kw)

        return wrapper

    return dec


def require_auth(scopes=[]):
    def dec(f):
        @functools.wraps(f)
        @provide_auth()
        def wrapper(*args, **kw):
            if not g.token and 'anonymous' not in scopes:
                return err('unauthorized', 'Unauthorized'), 401

            if g.token and g.token['scope'] not in scopes + ['all']:
                return err('forbidden', 'Forbidden'), 403

            return f(*args, **kw)

        return wrapper

    return dec


def charge_usage():
    def dec(f):
        @functools.wraps(f)
        def wrapper(*args, **kw):
            if g.account['balance'] < -1000:
                error = err(
                    'payment_required',
                    "Please request an invoice to replenish your account balance"
                )

                return error, 402

            now = time.time()
            res = f(*args, **kw)

            # Query cost is 1 msat per 100 ms runtime + 1 msat per kb payload, rounded up.
            ms = time.time() - now
            req_size = len(request.data.encode('utf-8'))
            res_size = len(json.dumps(res[0]).encode('utf-8'))
            cost = math.ceil(ms / 100 + req_size / 1024 + res_size / 1024)

            with pg.connect('master'):
                # Mutate the account in memory so the response header will be correct
                g.account['balance'] -= cost

                pg.execute(
                    "UPDATE account SET balance = %s WHERE id = %s",
                    [g.account['balance'], g.account['id']]
                )

            return res

        return wrapper

    return dec


class AccountResource(Resource):
    @require_auth(['anonymous', 'account/create'])
    def post(self):
        """
        Create a new account
        ---
        responses:
          201:
            description: Your new account information
            schema:
              properties:
                id:
                  type: string
                token:
                  type: string
        """
        account_id = random_uuid()
        token = token_hex()
        parent = getattr(g, 'account', None)

        if prop('parent', parent):
            return err('account_nesting', 'Child accounts cannot create child accounts'), 400

        with pg.connect('master'):
            pg.execute(
                "INSERT INTO account (id, parent) VALUES (%s, %s)",
                [account_id, prop('id', parent)]
            )

            pg.execute(
                "INSERT INTO token (id, account, value, scope) VALUES (%s, %s, %s, 'all')",
                [random_uuid(), account_id, token]
            )

        return {'id': account_id, 'token': token}, 201

    @require_auth()
    def delete(self):
        """
        Delete your account
        ---
        responses:
          204:
            description: Your account has been deleted
        """
        id = g.account['id']

        try:
            os.remove(sqlite.path(id))
        except FileNotFoundError:
            pass

        with pg.connect('master'):
            for child in pg.all('SELECT * FROM account WHERE parent = %s', [id]):
                try:
                    os.remove(sqlite.path(child['id']))
                    pg.execute("DROP SCHEMA %s", [child['id']])
                except FileNotFoundError:
                    pass

            pg.execute("DELETE FROM token WHERE account = %s", [id])
            pg.execute("DELETE FROM account WHERE parent = %s", [id])
            pg.execute("DELETE FROM account WHERE id = %s", [id])
            pg.execute("DROP SCHEMA %s", [id])

        return {}, 204


class TokenResource(Resource):
    @require_auth()
    def post(self):
        """
        Create a new access token
        ---
        parameters:
            - name: scope
              in: body
              description: The scope to create the token with
              required: true
              type: string
              enum:
                - account/create
                - all
                - all/readonly
        responses:
          201:
            description: Your new token
            schema:
              properties:
                id:
                  type: string
                token:
                  type: string
        """
        id = random_uuid()
        value = token_hex()
        scope = request.json['scope']

        if scope not in all_scopes:
            return err('enum', f'Scope must be one of {", ".join(all_scopes)}')

        with pg.connect('master'):
            pg.execute(
                "INSERT INTO token (id, account, value, scope) VALUES (%s, %s, %s, %s)",
                [id, g.account['id'], value, scope]
            )

        return {'id': id, 'token': value}, 201

    @require_auth()
    def delete(self):
        """
        Delete an access token
        ---
        parameters:
            - name: id
              in: body
              description: The token's id
              required: true
              type: string
        responses:
          204:
            description: Your token has been deleted
        """
        token_id = request.json['id']

        with pg.connect('master'):
            token_ids = pg.col('SELECT id FROM token WHERE account = %s', [g.account['id']])

            if token_id not in token_ids:
                return err('forbidden', 'Forbidden'), 403

            pg.execute("DELETE FROM token WHERE id = %s", [g.token['id']])

        return {}, 204


class InvoiceResource(Resource):
    @require_auth()
    def post(self):
        """
        Request a lightning invoice to pay for usage
        ---
        parameters:
            - name: amount_msat
              in: body
              description: An amount to pay in msats
              required: true
              type: integer
              minimum: 1000
        responses:
          200:
            description: Query results
            schema:
              properties:
                hash:
                  type: string
                bolt11:
                  type: string
                expires:
                  type: integer
        """
        bpt_id = env('IBEX_BPT_ID')
        secret = token_hex()
        amount_msat = request.json['amount_msat']

        if amount_msat < 1000:
            return err('mimimum', 'Amount must be greater than 1000 msats'), 400

        ibex_invoice = ibex.create_invoice_with_webhook(bpt_id, amount_msat, secret)

        with pg.connect('master'):
            pg.one(
                """INSERT INTO invoice
                     (account, hash, bolt11, expires, amount_msat, secret)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                [g.account['id'], ibex_invoice['hash'], ibex_invoice['bolt11'],
                 ibex_invoice['expirationUtc'], amount_msat, secret]
            )

        return {
            'hash': ibex_invoice['hash'],
            'bolt11': ibex_invoice['bolt11'],
            'expires': ibex_invoice['expirationUtc'],
        }, 201


class WebhookResource(Resource):
    def post(self):
        with pg.connect('master'):
            secret = request.json['secret']
            invoice = pg.one("SELECT * FROM invoice WHERE secret = %s", [secret])

            if invoice:
                pg.execute(
                    "UPDATE invoice SET status = 'settled' WHERE secret = %s",
                    [secret]
                )

                pg.execute(
                    "UPDATE account SET balance = balance + %s WHERE id = %s",
                    [invoice['amount_msat'], invoice['account']]
                )

        return {}, 200


class SqlResource(Resource):
    @require_auth(['readonly'])
    @charge_usage()
    def post(self):
        """
        Execute a query against your database
        ---
        parameters:
            - name: query
              in: body
              description: Your query
              required: true
              type: string
            - name: args
              in: body
              description: Parameters for your query
              required: false
              type: array
        responses:
          200:
            description: Query results
            schema:
              properties:
                data:
                  type: list
        """
        try:
            with sqlite.connect(g.account['id'], mode):
                data = sqlite.all(request.json['query'], request.json.get('args', []))
        except sqlite3.Error as exc:
            return err('query_error', exc.__str__()), 400

        return {'data': data}, 200


class ResourceResource(Resource):
    @require_auth()
    @charge_usage()
    def post(self, resource):
        """
        Create a resource instance
        ---
        parameters:
            - name: resource
              in: url
              description: The name of your resource
              required: true
              type: string
            - name: instance
              in: body
              description: The instance's data
              required: true
              type: object
        responses:
          200:
            description: Instance information
            schema:
              properties:
                id:
                  type: string
        """
        with pg.connect(g.account['id']):
            pg.ensure_resource(resource)

            instance_id = pg.insert_resource(resource, req.json['instance'])

        return {'id': instance_id}, 200


api.add_resource(AccountResource, '/account')
api.add_resource(TokenResource, '/token')
api.add_resource(InvoiceResource, '/invoice')
api.add_resource(SqlResource, '/sql')
api.add_resource(WebhookResource, '/webhook')
api.add_resource(ResourceResource, '/resource/<string:resource>')
#  api.add_resource(InstanceResource, '/resource/<string:resource>/<string:id>')
