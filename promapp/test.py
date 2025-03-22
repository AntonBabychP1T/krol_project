import json
import http.client
import pprint

# API Settings
AUTH_TOKEN = '17db24c397c3efba412926066166bf4c68e9d409'  # Вставте свій токен авторизації
HOST = 'my.prom.ua'  # Наприклад: my.prom.ua, my.satu.kz, my.prom.md

class HTTPError(Exception):
    pass

def make_request(method, url, token, body=None):
    connection = http.client.HTTPSConnection(HOST)
    headers = {
        'Authorization': 'Bearer {}'.format(token),
        'Content-type': 'application/json'
    }
    if body:
        body = json.dumps(body)
    connection.request(method, url, body=body, headers=headers)
    response = connection.getresponse()
    if response.status != 200:
        raise HTTPError('{}: {}'.format(response.status, response.reason))
    response_data = response.read()
    return json.loads(response_data.decode())

def get_last_10_orders(token):
    # Робимо запит до endpoint'у для отримання замовлень.
    # Якщо API підтримує параметр "limit", можна додати його в URL, наприклад:
    url = '/api/v1/orders/list?limit=10'
    # Але тут ми робимо запит без нього і обрізаємо результат.
    data = make_request('GET', url, token)
    orders = data.get('orders', [])
    # Обрізаємо список до перших 10 замовлень
    return orders[:10]

def main():
    if not AUTH_TOKEN:
        raise Exception("AUTH_TOKEN не задан!")
    try:
        orders = get_last_10_orders(AUTH_TOKEN)
        print("Останні 10 замовлень:")
        pprint.pprint(orders)
    except HTTPError as e:
        print("HTTP помилка:", e)

if __name__ == '__main__':
    main()
