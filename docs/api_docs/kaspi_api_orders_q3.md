3. Как с помощью API в Магазине на Kaspi.kz изменить статус заказа?
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

 

ACCEPTED_BY_MERCHANT

COMPLETED

 

 

 

CANCELLED 

 

 

 

ARRIVED 

ARRIVED_BACKWARD

 

 

 

ASSEMBLE

Принят

Выдан покупателю

Для заказов со статусом «ACCEPTED_BY_MERCHANT»

Отменен

Для заказов со статусом «ACCEPTED_BY_MERCHANT» или «APPROVED_BY_BANK»

Прибыл на склад

Для товаров по предзаказу

Возвращенный товар прибыл на склад

Для заказов со статусом CANCELLING или KASPI_DELIVERY_RETURN_REQUESTED

Скомплектован

Для заказов со статусом ACCEPTED_BY_MERCHANT

cancellationReason

Причина отмены

 

Необходима при статусе заказа CANCELLED

 

BUYER_CANCELLATION_BY_MERCHANT

• BUYER_NOT_REACHABLE

• MERCHANT_OUT_OF_STOCK

Покупатель отменил заказ

 

Не удалось связаться с покупателем

Товара нет в наличии

cancellationComment

Комментарий продавца

 

Для заказов со статусом CANCELLING

Максимум 1000 символов

 

 

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
"id": "ordersID=",
"attributes": {
"code": "ordercode ",
"status": "ARRIVED"
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
            "status": "ARRIVED"
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