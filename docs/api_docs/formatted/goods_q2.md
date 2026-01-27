# Как с помощью API в Магазине на Kaspi.kz узнать список характеристик товара?

*updated: 12.06.2024*

*canonical: /shop/api/goods/q3217*

Для этого отправьте API-запрос. Можно использовать любой сервис, например, Postman, Insomnia, Paw, Swagger, SoapUI или настроить интеграцию с вашей системой учета.

|  |  |
| --- | --- |
| **Параметр** | **Значение** |
| c | Код категории    *Чтобы его получить:*   * *с помощью* *API* *в Магазине на* *Kaspi**.**kz* *получите список характеристик категорий;* * *скопируйте значение атрибута «**code**».* |

Посмотреть пример запроса

Скопировано

```
GET
https://kaspi.kz/shop/api/products/classification/attributes?c=Master - Exercise notebooks&HTTP/1.1=&Host= kaspi.kz
Accept: application/json
X-Auth-Token: token
```

В ответе вы получите список атрибутов для каждой характеристики. Если вы передадите в них данные о товаре, они будут отображаться в его карточке в Магазине на Kaspi.kz.

|  |  |  |
| --- | --- | --- |
| **Атрибут** | | **Значение** |
| code | | Код характеристики |
| type | | Тип переменной, которую можно использовать для описания |
|  | boolean  enum  string  number | только «true» или «false»  значение из списка  текст  число |
| multiValued | | Можно указать несколько значений в характеристике |
|  | true  false | да  нет |
| mandatory | | Обязательно заполнять характеристику |
|  | true  false | да  нет |

Посмотреть пример ответа

Скопировано

```
 [
    {
        "code": "Exercise notebooks*Obsie harakteristiki.exercise notebooks*type",
        "type": "enum",
        "multiValued": false,
        "mandatory": true
    },
    {
        "code": "Exercise notebooks*Obsie harakteristiki.exercise notebooks*format",
        "type": "enum",
        "multiValued": true,
        "mandatory": true
    },
    {
        "code": "Exercise notebooks*Obsie harakteristiki.exercise notebooks*orientation",
        "type": "enum",
        "multiValued": false,
        "mandatory": false
    },
    {
        "code": "Exercise notebooks*Obsie harakteristiki.exercise notebooks*ruling",
        "type": "enum",
        "multiValued": false,
        "mandatory": true
    },
    {
        "code": "Exercise notebooks*Obsie harakteristiki.exercise notebooks*fields",
        "type": "boolean",
        "multiValued": false,
        "mandatory": true
    },
    {
        "code": "Exercise notebooks*Obsie harakteristiki.exercise notebooks*number of sheets",
        "type": "number",
        "multiValued": false,
        "mandatory": true
    },
    {
        "code": "Exercise notebooks*Obsie harakteristiki.exercise notebooks*number of notebooks",
        "type": "number",
        "multiValued": false,
        "mandatory": true
    },
    {
        "code": "Exercise notebooks*Obsie harakteristiki.exercise notebooks*paper whiteness",
        "type": "number",
        "multiValued": false,
        "mandatory": false
    },
    {
        "code": "Exercise notebooks*Obsie harakteristiki.exercise notebooks*framing",
        "type": "enum",
        "multiValued": true,
        "mandatory": true
    },
    {
        "code": "Exercise notebooks*Obsie harakteristiki.exercise notebooks*paper",
        "type": "enum",
        "multiValued": true,
        "mandatory": false
    },
    {
        "code": "Exercise notebooks*Obsie harakteristiki.exercise notebooks*base weight",
        "type": "number",
        "multiValued": false,
        "mandatory": false
    },
    {
        "code": "Exercise notebooks*Obsie harakteristiki.exercise notebooks*cover",
        "type": "enum",
        "multiValued": false,
        "mandatory": true
    },
    {
        "code": "Exercise notebooks*Obsie harakteristiki.exercise notebooks*decor",
        "type": "enum",
        "multiValued": true,
        "mandatory": false
    },
    {
        "code": "Exercise notebooks*Obsie harakteristiki.exercise notebooks*design",
        "type": "enum",
        "multiValued": true,
        "mandatory": false
    },
    {
        "code": "Exercise notebooks*Obsie harakteristiki.exercise notebooks*color",
        "type": "enum",
        "multiValued": true,
        "mandatory": true
    },
    {
        "code": "Exercise notebooks*Obsie harakteristiki.exercise notebooks*length",
        "type": "number",
        "multiValued": false,
        "mandatory": false
    },
    {
        "code": "Exercise notebooks*Obsie harakteristiki.exercise notebooks*width",
        "type": "number",
        "multiValued": false,
        "mandatory": false
    },
    {
        "code": "Exercise notebooks*Obsie harakteristiki.exercise notebooks*weight",
        "type": "number",
        "multiValued": false,
        "mandatory": false
    },
    {
        "code": "Exercise notebooks*Obsie harakteristiki.exercise notebooks*features",
        "type": "enum",
        "multiValued": true,
        "mandatory": false
    },
    {
        "code": "Exercise notebooks*Obsie harakteristiki.exercise notebooks*components",
        "type": "string",
        "multiValued": false,
        "mandatory": false
    },
    {
        "code": "Exercise notebooks*Obsie harakteristiki.exercise notebooks*additional",
        "type": "string",
        "multiValued": false,
        "mandatory": false
    },
    {
        "code": "Exercise notebooks*Obsie harakteristiki.exercise notebooks*notice",
        "type": "string",
        "multiValued": false,
        "mandatory": true
    },
    {
        "code": "Exercise notebooks*Obsie harakteristiki.exercise notebooks*range",
        "type": "enum",
        "multiValued": false,
        "mandatory": true
    }
]
```
