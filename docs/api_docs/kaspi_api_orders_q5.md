5. Как с помощью API в Магазине на Kaspi.kz сформировать накладную для передачи заказа на Kaspi Доставку?
Для этого измените статус товара на «Передача». Чтобы это сделать, отправьте API-запрос. Можно использовать любой сервис, например, Postman, Insomnia, Paw, Swagger, SoapUI или настроить интеграцию с вашей системой учета.

 

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

numberOfSpace

Количество накладных

 

Указывается самостоятельно

status

Статус заказа

 

В этом ответе — ASSEMBLE

 

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
"id": " ordersID",
"attributes": {
"status": "ASSEMBLE",
"numberOfSpace": "2"
}
}
}
 

В ответе вы получите информацию о заказе и его новый статус.

 

 Посмотреть пример ответа

 {
    "data": {
        "type": "orders",
        "id": "ordersID=",
        "attributes": {
            "numberOfSpace": 2,
            "status": "ASSEMBLE"
        },
        "relationships": {
            "user": {
                "links": {
                    "self": "https://kaspi.kz/shop/api/v2/orders/ordersID=/relationships/user",
                    "related": "https://kaspi.kz/shop/api/v2/orders/ordersID=/user"
                },
                "data": null
            },
            "entries": {
                "links": {
                    "self": "https://kaspi.kz/shop/api/v2/orders/ordersID=/relationships/entries",
                    "related": "https://kaspi.kz/shop/api/v2/orders/ordersID=/entries"
                }
            }
        },
        "links": {
            "self": "https://kaspi.kz/shop/api/v2/orders/ordersID="
        }
    },
    "included": []
}