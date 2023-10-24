import requests, functools
from json.decoder import JSONDecodeError
from raddoo import env, prop
from dotenv import load_dotenv


load_dotenv()


class IbexApiError(Exception):
    def __init__(self, message):
        super(IbexApiError, self).__init__(message)

        self.message = message


def _url(path):
    return '/'.join([env('IBEX_API_URL'), path])


@functools.lru_cache
def _get_access_token():
    res = requests.post(
        _url('auth/refresh-access-token'),
        json={'refreshToken': env('IBEX_REFRESH_TOKEN')}
    )

    return prop('accessToken', res.json())


def _headers():
    return {'Authorization': _get_access_token()}


def _req(method, path, **kw):
    res = requests.request(method, _url(path), headers=_headers(), **kw)

    try:
        json = res.json()
    except JSONDecodeError:
        raise IbexApiError(res.text)

    return json


def create_account(name):
    return _req('post', 'account', json={'name': name})


def get_account(id):
    return _req('get', f'account/{id}')


def create_bpt(account_id, name):
    return _req('post', 'bpt', json={
        'name': name,
        'accountId': account_id,
        'currencyId': 3,
    })


def list_transactions(bpt_id, period='all', limit=10, page=1):
    return _req('get', f'bpt/{bpt_id}/transactions', params={
        'period': period,
        'limit': limit,
        'page': page,
    })


def create_invoice(bpt_id, amount_msat):
    return _req('get', 'invoice/rest', params={
        'bpt_id': bpt_id,
        'amount_msat': amount_msat,
    })


def create_invoice_with_webhook(bpt_id, amount_msat, secret):
    return _req('post', 'invoice/rest/webhook', json={
        'bptId': bpt_id,
        'amountMsat': amount_msat,
        'webhookUrl': env('WEBHOOK_URL'),
        'webhookSecret': secret,
    })
