Для этого отправьте API-запрос.  Можно использовать любой сервис, например, Postman, Insomnia, Paw, Swagger, SoapUI или настроить интеграцию с вашей системой учета.

 

Параметр

Значение

filter[orders][code]

Номер заказа

 

Чтобы его узнать:

с помощью API в Магазине на Kaspi.kz получите список заказов;
скопируйте значение атрибута «code».
 

 Посмотреть пример запроса

GET
https://kaspi.kz/shop/api/v2/orders?filter[orders][code]=ordercode
ContentType: application/vnd.api+json
X-Auth-Token:token
 

В ответе вы получите информацию о заказе.

 

Атрибут

Значение

id

Уникальный код заказа

 

Для "type": "orders"

code

Номер заказа

totalPrice

Общая сумма заказа в тенге

customer

ФИО и номер телефона покупателя

paymentMode

Способ оплаты заказа

 

PAY_WITH_CREDIT

PREPAID

Кредит на Покупки

безналичная оплата

plannedDeliveryDate

Планируемая дата доставки

 

Указывается в миллисекундах

creationDate

Дата получения заказа

 

Указывается в миллисекундах

deliveryCostForSeller

Стоимость доставки для продавца

isKaspiDelivery

Kaspi Доставка

 

true

false

да

нет

deliveryMode

Способ доставки

 

DELIVERY_LOCAL

по городу — Kaspi Доставка или силами продавца

 	
DELIVERY_PICKUP

"isKaspiDelivery": true

DELIVERY_REGIONAL_TODOOR

"isKaspiDelivery": true

доставка в Kaspi Postomat

 

Kaspi Доставка

 	
DELIVERY_PICKUP

"isKaspiDelivery": false

DELIVERY_REGIONAL_PICKUP

самовывоз

 

доставка по области до склада с зоной выдачи заказов, покупатель заберет самовывозом

deliveryAddress

Адрес доставки

 

streetName

streetNumber

town

district

building

formattedAddress

 

 

latitude

longitude

улица

номер дома

город

район

номер строения

полный адрес

 

Географические координаты:

широта

долгота

signatureRequired

Подписать кредит

 

true

false

необходимо

не нужно

creditTerm

Срок Кредита на Покупки

preOrder

Оформлен по предзаказу

 

true

false

да

нет

pickupPointId

Уникальный код склада с зоной выдачи заказов

state

Состояние заказа

 

NEW

SIGN_REQUIRED

PICKUP
DELIVERY
KASPI_DELIVERY
ARCHIVE

новый

нужно подписать документы

самовывоз
ваша доставка
Kaspi Доставка
архивный

approvedByBankDate

Дата одобрения заказа банком

 

Указывается в миллисекундах

status

Статус заказа

 

APPROVED_BY_BANK

ACCEPTED_BY_MERCHANT

COMPLETED

CANCELLED

CANCELLING

KASPI_DELIVERY_RETURN_REQUESTED

RETURNED

продавец должен его принять

принят

завершен

отменен

в процессе отмены

ожидает возврата

возвращен

customer

Покупатель

 

id


 

name

firstName

lastName

Уникальный код клиента в системе Магазина на Kaspi.kz


Имя в системе Магазина на Kaspi.kz

Имя

Фамилия

deliveryCost

Стоимость доставки

 

 Посмотреть пример ответа

 {
    "data": [
        {
            "type": "orders",
            "id": "orderId",
            "attributes": {
                "code": "ordercode",
                "totalPrice": 4000.0,
                "paymentMode": "PAY_WITH_CREDIT",
                "plannedDeliveryDate": 1706896790999,
                "creationDate": 1706608613252,
                "deliveryCostForSeller": 0.0,
                "isKaspiDelivery": false,
                "deliveryMode": "DELIVERY_LOCAL",
                "deliveryAddress": {
                    "streetName": "улица Наурызбай батыра",
                    "streetNumber": "154А",
                    "town": "Алматы",
                    "district": null,
                    "building": null,
                    "apartment": null,
                    "formattedAddress": "Алматы, улица Наурызбай батыра, 154А",
                    "latitude": 43.240013,
                    "longitude": 76.938854
                },
                "signatureRequired": false,
                "creditTerm": 3,
                "preOrder": false,
                "pickupPointId": «merchant_PP1",
                "state": "DELIVERY",
                "approvedByBankDate": 1706608657792,
                "status": "ACCEPTED_BY_MERCHANT",
                "customer": {
                    "id": "customerId",
                    "name": null,
                    "cellPhone": "7750000000",
                    "firstName": "customerfirstname",
                    "lastName": "customerlastname"
                },
                "deliveryCost": 500.0
            },
            "relationships": {
                "user": {
                    "links": {
                        "self": "https://kaspi.kz/shop/api/v2/orders/orderId/relationships/user",
                        "related": "https://kaspi.kz/shop/api/v2/orders/orderId/user"
                    },
                    "data": {
                        "type": "customers",
                        "id": "customerId"
                    }
                },
                "entries": {
                    "links": {
                        "self": "https://kaspi.kz/shop/api/v2/orders/orderId/relationships/entries",
                        "related": "https://kaspi.kz/shop/api/v2/orders/orderId/entries"
                    }
                }
            },
            "links": {
                "self": "https://kaspi.kz/shop/api/v2/orders/orderId"
            }
        }
    ],
    "included": [],
    "meta": {
        "pageCount": 1,
        "totalCount": 1
    }
}