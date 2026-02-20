7. Как с помощью API в Магазине на Kaspi.kz получить описание товаров в заказе?
Для этого отправьте API-запрос. Можно использовать любой сервис, например, Postman, Insomnia, Paw, Swagger, SoapUI или настроить интеграцию с вашей системой учета.

 

Параметр

Значение

orderentriesID

Уникальный код заказа

 

Чтобы его узнать:

с помощью API в Магазине на Kaspi.kz получите состав заказа;
скопируйте значение атрибута «id» для "type": "orderentries".
 

 Посмотреть пример запроса

GET
https://kaspi.kz/shop/api/v2/orderentries/orderentriesID/product
Content-Type: application/vnd.api+json
X-Auth-Token: token
 

В ответе вы получите код товара в Магазине на Kaspi.kz, название и бренд.

 

Атрибут

Значение

id

Уникальный код товара в заказе

code

Код товара в Магазине на Kaspi.kz

name

Название

manufacturer

Бренд

category

Название категории

 

 Посмотреть пример ответа

{
    "data": {
        "type": "masterproducts",
        "id": "masterproductsId»,
        "attributes": {
            "code": "103403297",
            "name": "Фруктовик яблоко черный принц Польша 1 кг",
            "category": "Фрукты"
        },
        "relationships": {
            "merchantProduct": {
                "links": {
                    "self": "https://kaspi.kz/shop/api/v2/masterproducts/masterproductsID/relationships/merchantProduct",
                    "related": "https://kaspi.kz/shop/api/v2/masterproducts/masterproductsID/merchantProduct"
                },
                "data": null
            }
        },
        "links": {
            "self": "https://kaspi.kz/shop/api/v2/masterproducts/masterproductsID"
        }
    },
    "included": []
}