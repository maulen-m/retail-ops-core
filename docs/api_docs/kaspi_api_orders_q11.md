11. Как с помощью API в Магазине на Kaspi.kz получить описание одного товара в заказе?
Для этого отправьте API-запрос. Можно использовать любой сервис, например, Postman, Insomnia, Paw, Swagger, SoapUI или настроить интеграцию с вашей системой учета.

 

Параметр

Значение

masterproductsID==

Уникальный код товара в заказе

 

Чтобы его узнать:

с помощью API в Магазине на Kaspi.kz получите описание товара из заказа;
скопируйте значение атрибута «id» для "type": "masterproducts".
 

 Посмотреть пример запроса

GET
https://kaspi.kz/shop/api/v2/masterproducts/masterproductsID/merchantProduct
Content-Type: application/vnd.api+json
X-Auth-Token: token
 

В ответе вы получите код вашего товара, название и бренд.

 

Атрибут

Значение

id

Уникальный код товара продавца в заказе

code

Код товара в системе продавца

name

Название

manufacturer

Бренд

 

 Посмотреть пример ответа

 {
    "data": {
        "type": "merchantproducts",
        "id": "merchantproductsID»,
        "attributes": {
            "code": "103403297",
            "name": "Фруктовик яблоко черный принц Польша 1 кг"
        },
        "relationships": {},
        "links": {
            "self": "https://kaspi.kz/shop/api/v2/merchantproducts/merchantproductsID"
        }
    },
    "included": []
}