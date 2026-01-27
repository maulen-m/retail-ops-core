8. Как с помощью API в Магазине на Kaspi.kz получить информацию об одном товаре в заказе?
Для этого отправьте API-запрос. Можно использовать любой сервис, например, Postman, Insomnia, Paw, Swagger, SoapUI или настроить интеграцию с вашей системой учета.

 

Параметр

Значение

orderentriesId=

Уникальный код товара в заказе

 

Чтобы его узнать:

с помощью API в Магазине на Kaspi.kz получите информацию о товарах в заказе;
скопируйте значение атрибута «id» для "type": "orderentries".
 

 Посмотреть пример запроса

GET
https://kaspi.kz/shop/api/v2/orderentries/orderentriesId=
ContentType: application/vnd.api+json
X-Auth-Token:token
 

В ответе вы получите стоимость каждого товара, а также информацию, сколько таких товаров купил клиент.

Атрибут

Значение

id

Уникальный код товара в заказе

unitType

Тип товара

 

MEASURABLE_PIECES

MEASURABLE

PIECES

цельно-весовой

весовой

штучный

minAllowedWeight

Минимальный вес товара

quantity

Количество каждого товара в заказе

totalPrice

Общая стоимость заказа

weight

Вес товара

 

Только для товаров, у которых указан вес

entryNumber

Порядковый номер товара в заказе

code

Код категории

title

Название категории

deliveryCost

Стоимость доставки

basePrice

Стоимость товара

 

 Посмотреть пример ответа

 {
    "data": {
        "type": "orderentries",
        "id": "orderentriesId",
        "attributes": {
            "unitType": "MEASURABLE_PIECES",
            "minAllowedWeight": 1000.0,
            "quantity": 3,
            "totalPrice": 5928.0,
            "weight": 3800.0,
            "entryNumber": 0,
            "category": {
                "code": "Master - Umbrellas",
                "title": "Зонты"
            },
            "deliveryCost": 0.0,
            "basePrice": 1560.0
        },
        "relationships": {
            "deliveryPointOfService": {
                "links": {
                    "self": "https://kaspi.kz/shop/api/v2/orderentries/orderentriesId/relationships/deliveryPointOfService",
                    "related": "https://kaspi.kz/shop/api/v2/orderentries/orderentriesId/deliveryPointOfService"
                },
                "data": {
                    "type": "pointofservices",
                    "id": "pointofservicesId"
                }
            },
            "product": {
                "links": {
                    "self": "https://kaspi.kz/shop/api/v2/orderentries/orderentriesId/relationships/product",
                    "related": "https://kaspi.kz/shop/api/v2/orderentries/orderentriesId/product"
                },
                "data": {
                    "type": "masterproducts",
                    "id": "masterproductsId"
                }
            }
        },
        "links": {
            "self": "https://kaspi.kz/shop/api/v2/orderentries/orderentriesId"
        }
    },
    "included": []
}