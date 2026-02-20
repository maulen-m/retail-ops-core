Для этого отправьте API-запрос. Можно использовать любой сервис, например, Postman, Insomnia, Paw, Swagger, SoapUI или настроить интеграцию с вашей системой учета.

|  |  |  |
| --- | --- | --- |
| **Параметр** | | **Значение** |
| page[number] | | Номер страницы с результатом запроса    *На одной странице может быть максимум 100 заказов*    *Укажите номер нужной страницы, начиная с 0* |
| page[size] | | Количество заказов, которое будет на одной странице в ответе    *Максимум — 100* |
| filter[orders][state] | | Состояние заказа |
|  | NEW  SIGN\_REQUIRED  PICKUP  DELIVERY  KASPI\_DELIVERY  ARCHIVE | новый  нужно подписать документы  самовывоз  ваша доставка  Kaspi Доставка  архивный |
| filter[orders][creationDate] | | Дата создания заказа    *Указывается в миллисекундах* |
|  | [$ge]  [$le] | начальное значение  конечное значение |
| filter[orders][status] | | Статус заказа |
|  | APPROVED\_BY\_BANK  ACCEPTED\_BY\_MERCHANT  COMPLETED  CANCELLED  CANCELLING  KASPI\_DELIVERY\_RETURN\_REQUESTED  RETURNED | продавец должен его принять  принят  завершен  отменен  в процессе отмены  ожидает возврата  возвращен |
| filter[orders][deliveryType] | | Способ доставки    *Используйте, только если* *filter**[**orders**][**state**] не равен PICKUP*  *DELIVERY, KASPI\_DELIVERY* *или* *PICKUP* |
|  | PICKUP  DELIVERY | самовывоз  доставка |
| filter[orders][signatureRequired] | | Подписание документов    *Используйте, если* *filter**[**orders**][**state**] не равен* *SIGN**\_**REQUIRED* |
|  | true  false | необходимо  не требуется |
| include[orders] | | Дополнительные данные о заказе |
|  | user | Информация о покупателе, который оформил заказ |

Посмотреть пример запроса

Скопировано

```
GET
https://kaspi.kz/shop/api/v2/orders?page[number]=0&page[size]=20&filter[orders][state]=NEW
&filter[orders][creationDate][$ge]=1478736000000&filter[orders][creationDate][$le]=1479945600000
&filter[orders][status]=APPROVED_BY_BANK&filter[orders][deliveryType]=PICKUP
&filter[orders][signatureRequired]=false&include[orders]=user
Content-Type:application/vnd.api+json
X-Auth-Token: <token>
```

В ответе вы получите информацию о каждом заказе.

|  |  |  |
| --- | --- | --- |
| **Атрибут** | | **Значение** |
| code | | Номер заказа |
| totalPrice | | Общая сумма заказа в тенге |
| customer | | ФИО и номер телефона покупателя |
| deliveryMode | | Способ доставки |
|  | DELIVERY\_LOCAL | по городу — Kaspi Доставка или силами продавца |
| DELIVERY\_PICKUP  "isKaspiDelivery": true  DELIVERY\_REGIONAL\_TODOOR  "isKaspiDelivery": true | доставка в Kaspi Postomat    Kaspi Доставка |
| DELIVERY\_PICKUP  "isKaspiDelivery": false  DELIVERY\_REGIONAL\_PICKUP | самовывоз    доставка по области до склада с зоной выдачи заказов, покупатель заберет самовывозом |
| paymentMode | | Способ оплаты заказа |
|  | PAY\_WITH\_CREDIT  PREPAID | Кредит на Покупки  безналичная оплата |
| signatureRequired | | Подписать кредит |
|  | true  false | необходимо  не нужно |
| creditTerm | | Срок Кредита на Покупки |
| preOrder | | Оформлен по предзаказу |
|  | true  false | да  нет |
| state | | Состояние заказа |
|  | NEW  SIGN\_REQUIRED  PICKUP  DELIVERY  KASPI\_DELIVERY  ARCHIVE | новый  нужно подписать документы  самовывоз  ваша доставка  Kaspi Доставка  архивный |
| creationDate | | Дата создания заказа    *Указывается в миллисекундах* |
| approvedByBankDate | | Дата одобрения заказа банком    *Указывается в миллисекундах* |
| plannedDeliveryDate | | Планируемая дата доставки    *Указывается в миллисекундах* |
| reservationDate | | Дата доставки по предзаказу    *Указывается в миллисекундах* |
| status | | Статус заказа |
|  | APPROVED\_BY\_BANK  ACCEPTED\_BY\_MERCHANT  COMPLETED  CANCELLED  CANCELLING  KASPI\_DELIVERY\_RETURN\_REQUESTED  RETURNED | продавец должен его принять  принят  завершен  отменен  в процессе отмены  ожидает возврата  возвращен |
| deliveryCost | | Стоимость доставки |
| isImeiRequired | | IMEI-код товара в заказе |
|  | true  false | необходимо указать  код не нужен |
| id | | Уникальный код |
| waybill | | Ссылка на накладную    *Необходимо распечатать и прикрепить на заказы для* *Kaspi* *Доставки* |
| courierTransmissionPlanningDate | | Планируемая дата передачи заказа курьеру Kaspi Доставки    *Указывается в миллисекундах* |
| courierTransmissionDate | | Фактическая дата передачи заказа курьеру    *Указывается в миллисекундах* |
| deliveryAddress | | Адрес доставки |
| waybillNumber | | Номер накладной |
| category | | Категория товара |
| deliveryCostForSeller | | Стоимость доставки для продавца |
| express | | Покупатель выбрал Express-доставку |
|  | true  false | да  нет |
| returnedToWarehouse | | Заказ возвращен в пункт приема |
|  | true  false | да  нет |
| entries | | Состав заказа |
| user | | Покупатель |

Посмотреть пример ответа

Скопировано

```
{
```

"data": [

{

"type": "orders",

"id": "orderID",

"attributes": {

"customer": {

"firstName": "Иван Иваныч",

"lastName": "Иванов",

"cellPhone": "7xx0xxxxxx"

},

"code": "ordercode",

"totalPrice": 96045,

"deliveryMode":

"DELIVERY\_PICKUP",

"paymentMode": "PAY\_WITH\_CREDIT",

"signatureRequired": false,

"state": "PICKUP",

"creationDate": 1479470446241,

"approvedByBankDate":1479470451108,

"status": "ACCEPTED\_BY\_MERCHANT",

"deliveryCost": 1000,

"isImeiRequired": false

},

"relationships": {

"entries": {

"links": {

"self": "/v2/orders/orderID/relationships/entries",

"related": "/v2/orders/orderID/entries"

}

},

"user": {

"links": {

"self": "/v2/orders/orderID/relationships/user",

"related": "/v2/orders/orderID/user"

},

"data": {

"type": "customers",

"id": "customerID"

}

}

},

"links": {

"self": "/v2/orders/orderID"

}

}

],

"included": [

{

"type": "customers",

"id": "customerID",

"attributes": {

"firstName": "Иван",

"lastName": "Иваныч",

"cellPhone": "7xx0xxxxxx"

},

"relationships": {},

"links": {

"self":"/v2/customers/customerID"

}

}

],

"meta": {

"pageCount": 1,

"totalCount": 1

}

}