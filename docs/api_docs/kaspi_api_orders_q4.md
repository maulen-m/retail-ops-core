4. Как с помощью API в Магазине на Kaspi.kz получить информацию о товарах в моем заказе?
Для этого отправьте API-запрос. Можно использовать любой сервис, например, Postman, Insomnia, Paw, Swagger, SoapUI или настроить интеграцию с вашей системой учета.

 

Параметр

Значение

orderId

Уникальный код заказа

 

Чтобы его узнать:

с помощью API в Магазине на Kaspi.kz получите информацию о составе заказа;
скопируйте значение атрибута «id» для "type": "orders".
 

 Посмотреть пример запроса

GET
https://kaspi.kz/shop/api/v2/orders/orderID/entries
ContentType: application/vnd.api+json
X-Auth-Token:token
 

В ответе вы получите информацию о стоимости заказа и всех товаров, а также об их количестве.

 

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

quantity

Количество каждого товара в заказе

totalPrice

Общая стоимость заказа

weight

Вес товара

 

Только для товаров, у которых указан вес

entryNumber

Порядковый номер товара в заказе

category

Код категории

title

Название категории

deliveryCost

Стоимость доставки

basePrice

Стоимость товара

isImeiRequired	IMEI-код товара в заказе
 	true
false

необходимо указать
код не нужен

 

 Посмотреть пример ответа

 {
    "data": [

        {

            "type": "orderentries",

            "id": "orderentriesId»,

            "attributes": {

                "unitType": "PIECES",

                "quantity": 2,

                "totalPrice": 4000.0,

                "weight": 2000.0,

                "entryNumber": 0,

                "category": {

                    "code": "Master - Fruits",

                    "title": "Фрукты"

                },

                "deliveryCost": 500.0,

                "basePrice": 2000.0,

"isImeiRequired": false

            },

            "relationships": {

                "deliveryPointOfService": {

                    "links": {

                        "self": "https://kaspi.kz/shop/api/v2/orderentries/orderentriesId/relationships/deliveryPointOfService",

                        "related": "https://kaspi.kz/shop/api/v2/orderentries/orderentriesId/deliveryPointOfService"

                    },

                    "data": {

                        "type": "pointofservices",

                        "id": "pointofservicesId»

                    }

                },

                "product": {

                    "links": {

                        "self": "https://kaspi.kz/shop/api/v2/orderentries/orderentriesId/relationships/product",

                        "related": "https://kaspi.kz/shop/api/v2/orderentries/orderentriesId/product"

                    },

                    "data": {

                        "type": "masterproducts",

                        "id": "masterproductsId»

                    }

                }

            },

            "links": {

                "self": "https://kaspi.kz/shop/api/v2/orderentries/orderentriesId"

            }

        }

    ],

    "included": []

}