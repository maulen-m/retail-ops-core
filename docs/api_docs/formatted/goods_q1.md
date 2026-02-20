# Как с помощью API добавить товар для продажи в Магазине на Kaspi.kz?

*updated: 12.06.2024*

*canonical: /shop/api/goods/q3219*

Для этого отправьте API-запрос. Можно использовать любой сервис, например, Postman, Insomnia, Paw, Swagger, SoapUI или настроить интеграцию с вашей системой учета.

|  |  |
| --- | --- |
| **Параметр** | **Значение** |
| sku | Артикул товара |
| title | Название товара |
| brand | Бренд |
| category | Код категории    *Чтобы его получить:*   * *с помощью* *API* *в Магазине на* *Kaspi**.**kz* *получите список категорий;* * *скопируйте значение атрибута «**code**».* |
| description | Описание от продавца |
| images | Фотографии товара    *Укажите ссылку на изображение в ключе «**url**»* |

|  |  |
| --- | --- |
| **Атрибут** | **Значение** |
| code | Код характеристики товара    *Чтобы его получить:*   * *с помощью* *API* *в Магазине на* *Kaspi**.**kz* *получите список характеристик для категории;* * *скопируйте значение атрибута «**code**».* |
| value | Значение характеристики |

Посмотреть пример запроса

Скопировано

```
POST /shop/api/products/import HTTP/1.1
Host: kaspi.kz
Accept: application/json
X-Auth-Token: token
Content-Type: text/plain
 
//body
 
[
 
  {
 
    "sku": "Testsku»,
    "title": "test notebook",
    "brand": "test",
    "category": "Master - Exercise notebooks",
    "description": "Some description",
    "attributes": [
            {
        "code": "Exercise notebooks*Obsie harakteristiki.exercise notebooks*type",
        "value": "тетрадь-блокнот"
      },
      {
 
        "code": "Exercise notebooks*Obsie harakteristiki.exercise notebooks*format",
        "value": "А5"
      },
      {
        "code": "Exercise notebooks*Obsie harakteristiki.exercise notebooks*orientation",
        "value": "вертикальная"
      },
      {
        "code": "Exercise notebooks*Obsie harakteristiki.exercise notebooks*ruling",
        "value": "крупная клетка"
      },
      {
        "code": "Exercise notebooks*Obsie harakteristiki.exercise notebooks*fields",
        "value": true
      },
      {
        "code": "Exercise notebooks*Obsie harakteristiki.exercise notebooks*number of sheets",
        "value": 48
      },
      {
        "code": "Exercise notebooks*Obsie harakteristiki.exercise notebooks*number of notebooks",
        "value": 2
      },
      {
        "code": "Exercise notebooks*Obsie harakteristiki.exercise notebooks*framing",
        "value": "резинка"
      },
      {
        "code": "Exercise notebooks*Obsie harakteristiki.exercise notebooks*paper",
        "value": "офсетная"
      },
      {
        "code": "Exercise notebooks*Obsie harakteristiki.exercise notebooks*cover",
        "value": "мягкая"
      },
      {
        "code": "Exercise notebooks*Obsie harakteristiki.exercise notebooks*color",
        "value": "желтый"
      },
      {
        "code": "Exercise notebooks*Obsie harakteristiki.exercise notebooks*notice",
        "value": "тестест"
      },
      {
        "code": "Exercise notebooks*Obsie harakteristiki.exercise notebooks*range",
        "value": "расцветка в зависимости от наличия на складе"
      }
         ],
    "images": [
      {
        "url": "https://resources.cdn-kaspi.kz/img/m/p/h44/h88/63854412398622.jpg"
      }
    ]
  }
]
```

В ответе вы получите уникальный код загрузки товара и результат его добавления в Магазин на Kaspi.kz.

Посмотреть пример ответа

Скопировано

```
{
    "code": "testproduct",
    "status": "UPLOADED"
}
```
