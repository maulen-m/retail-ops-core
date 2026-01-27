6. Как с помощью API в Магазине на Kaspi.kz принять новый заказ?
Для этого отправьте API-запрос. Можно использовать любой сервис, например, Postman, Insomnia, Paw, Swagger, SoapUI или настроить интеграцию с вашей системой учета.

 

Параметр

Значение

type

Тип объекта

 

В этом запросе — orders

id

Уникальный код заказа

 

Чтобы его узнать:

с помощью API в Магазине на Kaspi.kz получите информацию о составе заказа;
скопируйте значение атрибута «id» для "type": "orders".
 

Атрибут

Значение

Code

Номер заказа

 

Чтобы его узнать:

с помощью API в Магазине на Kaspi.kz получите список заказов;
скопируйте значение атрибута «code».
Status

Статус заказа

 

В этом ответе — ACCEPTED_BY_MERCHANT

 

 Посмотреть пример запроса

https://kaspi.kz/shop/api/v2/orders
POST /api/v2/orders
HTTP/1.1
Host: kaspi.kz/shop
Content-Type: application/vnd.api+json
X-Auth-Token:token
{
"data":
{
"type": "orders",
"id": "ordersID",
"attributes": {
"code": "ordercode",
"status": "ACCEPTED_BY_MERCHANT"
}
}
 

В ответе вы получите информацию о заказе и его новый статус.

 

 Посмотреть пример ответа

 {
    "data": {
        "type": "orders",
        "id": "ordersID",
        "attributes": {
            "code": "ordercode",
            "status": "ACCEPTED_BY_MERCHANT"
        },
        "relationships": {
            "user": {
                "links": {
                    "self": "https://kaspi.kz/shop/api/v2/orders/ordersID/relationships/user",
                    "related": "https://kaspi.kz/shop/api/v2/orders/ordersID/user"
                },
                "data": null
            },
            "entries": {
                "links": {
                    "self": "https://kaspi.kz/shop/api/v2/orders/ordersID/relationships/entries",
                    "related": "https://kaspi.kz/shop/api/v2/orders/ordersID/entries"
                }
            }
        },
        "links": {
            "self": "https://kaspi.kz/shop/api/v2/orders/ordersID"
        }
    },
    "included": []
}