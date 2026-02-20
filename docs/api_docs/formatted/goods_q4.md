# Как с помощью API в Магазине на Kaspi.kz узнать код категории для добавления товара?

*updated: 12.06.2024*

*canonical: /shop/api/goods/q3216*

Для этого отправьте API-запрос. Можно использовать любой сервис, например, Postman, Insomnia, Paw, Swagger, SoapUI или настроить интеграцию с вашей системой учета.

Посмотреть пример запроса

Скопировано

```
GET /shop/api/products/classification/categories HTTP/1.1
Host: kaspi.kz
Accept: application/json
X-Auth-Token: token
```

В ответе вы получите названия категорий и их коды для API-запросов.

|  |  |
| --- | --- |
| **Атрибут** | **Значение** |
| code | Код категории для API-запроса |
| title | Название категории в Магазине на Kaspi.kz |

Посмотреть пример ответа

Скопировано

```
 [
    {
        "code": "Master - Exercise notebooks",
        "title": "Тетради"
    },
    {
        "code": "Master - Head units",
        "title": "Автомагнитолы"
    },
    {
        "code": "Master - Car alarms",
        "title": "Автосигнализации"
    },
    {
        "code": "Master - Blenders",
        "title": "Блендеры"
    },
    {
        "code": "Master - Cooktops",
        "title": "Варочные поверхности"
    },
    {
        "code": "Master - Video cameras",
        "title": "Видеокамеры"
    },
    {
        "code": "Master - Videocards",
        "title": "Видеокарты"
    },
    {
        "code": "Master - DVRs",
        "title": "Видеорегистраторы"
    }
]
```
