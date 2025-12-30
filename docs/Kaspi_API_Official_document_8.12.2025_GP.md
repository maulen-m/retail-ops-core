Kaspi Shop API – Merged Documentation (Orders and Products)
1. General information about the API in Kaspi Shop
1.1 How to use the API in Kaspi Shop?

To use the API in Kaspi Shop:

Generate an authorization token in the web version of the seller’s account.
Go to the Settings → API token section and click Generate.

Send a test API request.
You can use any service, for example Postman, Insomnia, Paw, Swagger, SoapUI, or integrate it with your accounting system.

Check the response.
The HTTP status code must be 200.

Integrate the API with your accounting system (for example, 1C).

Send API requests in order to:

add new products;

process orders and receive information about them.

You can do this yourself or pass the token and documentation to the technical specialist in your company so that they can integrate Kaspi Shop with your accounting system and configure work via the API.

1.2 How to get an authorization token in Kaspi Shop?

Only the head of the company can obtain an authorization token.

To do this:

Log in to the web version of the Kaspi Shop seller’s account.
Use the phone number you use to log in to the Kaspi Pay mobile app, and enter your password.

Go to Settings → API token.

Click Generate and copy the token.
You can do this at any time; your token will not change.

Do not share the token code with anyone except your company’s technical specialist. Anyone who has the token will be able to obtain information about orders and products from your seller’s account.

1.3 What is the API in Kaspi Shop?

API (Application Programming Interface) is a program interface that allows Kaspi Shop sellers to:

add new products;

process orders and receive information about them;

integrate their accounting system with Kaspi Shop.

This allows partners to save time and avoid errors in their inventory records.

For example, you need to complete an order.
Send an API request: the order status will change to “COMPLETED” (Issued to the buyer), and this information will appear in your accounting system.

The API in Kaspi Shop uses the JSON data format.

1.4 Which software can Kaspi Shop be integrated with?

You can integrate Kaspi Shop with your own accounting system, for example:

1C

Rkeeper

Paloma

Umag

and other software.

To do this, pass the authorization token to the technical specialist in your company.
You can also configure the integration with your accounting system yourself.

1.5 What is an API request in Kaspi Shop?

An API request is an instruction that Kaspi Shop receives from a seller or technical specialist.

The request describes who wants to get the data and what information needs to be returned in the response.

An API request in Kaspi Shop must contain:

Method

Describes the action:

GET — retrieves data.

PUT — updates data or adds new data.

POST — uploads information.

Parameters

Conditions according to which the response will be formed.
In Kaspi Shop each request uses its own set of parameters.

Examples:

sort — sorting of the result;

page — which page is returned in the response and how many values are on it;

filter — filtering by entity/field.

Headers

Additional information for correct processing of the instruction:

Content-Type — data transfer format. In Kaspi Shop it is application/vnd.api+json.

X-Auth-Token — authorization token.

Accept — the content type that is required in the response.

Attributes can also be used in the API request — these are descriptions of the data that will be in the response.

1.6 What is a response to an API request in Kaspi Shop?

A response is the information that Kaspi Shop returns to an API request.

The data is passed in attributes.
In each response they are different — this depends on the purpose of the request.

If the request is completed successfully, the HTTP status code of the response will be 200.
Any other status means that there is an error in the request or the server is not responding.

1.7 How to get a city code for an API request in Kaspi Shop?

To get a city code, select the required city in the table and copy its code.

Examples:

353220100 — Абай

113220100 — Акколь

273620100 — Аксай

551610000 — Аксу

471010000 — Актау

151010000 — Актобе

750000000 — Алматы

634820100 — Алтай

433220100 — Аральск

391610000 — Аркалык

511610000 — Арысь

710000000 — Астана

231010000 — Атырау

633420100 — Аягоз

431910000 — Байконыр

351610000 — Балхаш

473630100 — Бейнеу

194020100 — Есик

471810000 — Жанаозен

195620100 — Жаркент

351810000 — Жезказган

514420100 — Жетысай

394420100 — Житикара

634620100 — Зайсан

154820100 — Кандыагаш

351010000 — Караганда

316220100 — Каратау

195220100 — Каскелен

612010000 — Кентау

111010000 — Кокшетау

191610000 — Конаев

391010000 — Костанай

233620100 — Кульсары

632210000 — Курчатов

431010000 — Кызылорда

515820100 — Ленгер

392010000 — Лисаковск

551010000 — Павлодар

591010000 — Петропавловск

156420100 — Риддер

392410000 — Рудный

352210000 — Сарань

515420100 — Сарыагаш

352310000 — Сатпаев

632810000 — Семей

111810000 — Степногорск

196220100 — Талгар

191010000 — Талдыкорган

311010000 — Тараз

192610000 — Текели

352410000 — Темиртау

512610000 — Туркестан

271010000 — Уральск

631010000 — Усть-Каменогорск

195020100 — Уштобе

475220100 — Форт-Шевченко

156020100 — Хромтау

616420100 — Шардара

352810000 — Шахтинск

636820100 — Шемонаиха

117055900 — Шиели

316621100 — Шу

511010000 — Шымкент

117020100 — Щучинск

552210000 — Экибастуз

634030100 — п. Глубокое

554230100 — п. Железинка

474239100 — п. Жетыбай

474230100 — п. Курык

395430100 — п. Тобыл

474630100 — п. Шетпе

515230100 — с. Аксукент

153220100 — с. Алга

271035100 — с. Зачаганск

314851205 — с. Кордай

116651100 — с. Косшы

194230100 — с. Узынагаш

Use the corresponding code in API requests where a city parameter is required.

1.8 What is an authorization token in Kaspi Shop?

An authorization token is a unique code required to access the Kaspi Shop seller’s account.

The token confirms that API requests are sent by the company head or technical specialist, and that responding to them is safe.

Do not share the token code with anyone except your company’s technical specialist.
Anyone who has the token will be able to obtain information about orders and products from your seller’s account.

1.9 How to place the “Buy on Credit” button on my website?

To place a “Buy on Credit” button:

Add the button code to the page’s HTML.

Fill the attributes with your own values.

Attributes:

data-merchant-sku — the product SKU that you use in Kaspi Shop.

data-merchant-code — your shop code.
Copy it in the web version of the seller’s account: Settings → Shop ID.

data-city — city code.

Choose a button depending on where you place it.

Product description page

Flat button (flatButton)

<!-- main way to add button on page  -->
<div class="ks-widget"
     data-template="flatButton"
     data-merchant-sku="data-merchant-sku"
     data-merchant-code="data-merchant-code"
     data-city="750000000"
     data-style="desktop"
></div>


Red button

<!-- main way to add button on page  -->
<div class="ks-widget"
     data-template="button"
     data-merchant-sku="data-merchant-sku"
     data-merchant-code="data-merchant-code"
     data-city="750000000"
></div>


Blue button

<!-- main way to add button on page  -->
<div class="ks-widget"
     data-template="button"
     data-merchant-sku="data-merchant-sku"
     data-merchant-code="data-merchant-code"
     data-city="750000000"
     data-style="bigBlue"
></div>


If you place a dynamic button, call ksWidgetInitializer.reinit() after the <div> with the widget is added to the DOM.

To check this, press F12 on the needed page and find the tag in the developer tools panel.

The <script> code must be placed once — before the closing </body> tag.

Dynamic button

<!-- it's a placeholder for dynamic example -->
<div id="dynamic"></div>

<!-- onpage script, should be added once, before closing </body> -->
<script>(function(d, s, id) {
    var js, kjs;
    if (d.getElementById(id)) return;
    js = d.createElement(s); js.id = id;
    js.src = 'https://kaspi.kz/kaspibutton/widget/ks-wi_ext.js';
    kjs = document.getElementsByTagName(s)[0]
    kjs.parentNode.insertBefore(js, kjs);
}(document, 'script', 'KS-Widget'));</script>

<!-- Example: adding another button placeholder dynamically after 1sec -->
<script>
  setTimeout(function () {
      document.getElementById('dynamic').innerHTML =
        '<div class="ks-widget" data-template="button" data-merchant-sku="data-merchant-sku" data-merchant-code="data-merchant-code" data-city="750000000"></div>';
      // you should run this method to recheck buttons in DOM:
      ksWidgetInitializer.reinit()
  }, 1000)
</script>


Small button

<!-- main way to add button on page  -->
<div class="ks-widget"
     data-template="flatButton"
     data-merchant-sku="data-merchant-sku"
     data-merchant-code="data-merchant-code"
     data-city="750000000"
     data-style="small"
></div>

Mobile version of the website

Button for the mobile version

<!-- main way to add button on page  -->
<div class="ks-widget"
     data-template="flatButton"
     data-merchant-sku="data-merchant-sku"
     data-merchant-code="data-merchant-code"
     data-city="750000000"
     data-style="mobile"
></div>


When a customer clicks the button, the product card in Kaspi Shop will open and the client will be able to submit a Kaspi Credit for Purchases application.

2. Orders API – JSON:API specification
2.1 Orders API overview

The Orders API (Application Programming Interface) for Kaspi Shop sellers is a program interface designed to obtain information about orders and related data that come through the Kaspi Shop platform.

This program interface complies with the JSON API specification.
The specification describes how client–server systems interact, based on JSON message format and the HTTP protocol.

Each request to the system is accompanied by headers and a set of parameters.

Required headers

Content-Type – MIME type of the request body.
Must be set to: application/vnd.api+json.

X-Auth-Token – authorization token.
A unique identifier that allows access to the program interface.
You can generate the authorization token yourself in your personal account.

The set of parameters passed with a request can differ.
Parameters can be:

required;

optional.

Parameters also differ by how they modify the retrieved data:

Sorting – described using the sort keyword and the field by which sorting is applied.
Example: sort=age sorts by the age field in ascending order.

Pagination – described using the page keyword and an additional parameter.
Example: page[number]=1 and page[size]=20 will retrieve the first page of results where each page contains 20 values.

Filtering – specified using the filter keyword, the entity, and the field to be filtered.
Example: filter[orders][status]=COMPLETED means all orders whose status field equals COMPLETED will be selected.

Filters support optional operators:

$lt – (lower than) retrieves values less than the value specified in the filter;

$gt – (greater than) retrieves values greater than the value specified in the filter;

$le – (lower or equal to) retrieves values less than or equal to the value specified in the filter;

$ge – (greater or equal to) retrieves values greater than or equal to the value specified in the filter.

Example of a filter with operators:

filter[orders][creationDate][$ge]=1741428892000

filter[orders][creationDate][$le]=1742465692000

This means the order creation date will be:

greater than or equal to 8 March 2025, and

less than or equal to 20 March 2025.

Filter values are specified in milliseconds as a Timestamp.
All dates are specified in the Almaty timezone.

Important: the set of parameters passed in each request may be different, and the service does not guarantee support for sorting, filtering, and pagination in cases not described in this documentation.

Response structure

The response to a request can contain the following top-level objects:

data – an array of entities satisfying the request parameters.

Each entity contains the following sub-objects:

type – string identifier of the entity type.

id – string identifier of the entity.

attributes – object with all entity attributes.

relationships – object with all entity relationships.
Relationships may point either to multiple objects that are part of the current entity or to a single object.

links – additional links.

Other objects:

included – nested entities included in the request.
You can specify which nested entities to include via the include parameter.
Example: include[orders]=user means the user entity included in orders will be included in the response.

meta – meta-information such as number of pages or total number of results.

2.2 Request variants
2.2.1 Getting a list of orders

Description

This request returns a list of orders placed by customers.
It contains the total order price, delivery and payment types, status, state, and creation and bank approval dates.

Request

GET https://kaspi.kz/shop/api/v2/orders?page[number]=0&page[size]=20&filter[orders][state]=NEW
  &filter[orders][creationDate][$ge]=1735728014000&filter[orders][creationDate][$le]=1736764814000
  &filter[orders][status]=APPROVED_BY_BANK&filter[orders][deliveryType]=PICKUP
  &filter[orders][signatureRequired]=false&include[orders]=entries
Content-Type: application/vnd.api+json
X-Auth-Token: <token>


Response (fragment)

{
  "data": [
    {
      "type": "orders",
      "id": "NDk3MTQ6MDIx",
      "attributes": {
        "code": "496149022",
        "totalPrice": 2000.0,
        "paymentMode": "PAY_WITH_CREDIT",
        "creationDate": 1739349620761,
        "deliveryCostForSeller": 0.0,
        "reservationDate": 1739797300000,
        "isKaspiDelivery": false,
        "deliveryMode": "DELIVERY_PICKUP",
        "signatureRequired": false,
        "creditTerm": 3,
        "preOrder": false,
        "pickupPointId": "Merchant_00005678",
        "state": "PICKUP",
        "approvedByBankDate": 1739349626600,
        "status": "ACCEPTED_BY_MERCHANT",
        "customer": {
          "id": "NzA3NjgyODAwNg",
          "name": null,
          "cellPhone": "7066828008",
          "firstName": "Даниела",
          "lastName": "Муталидзе"
        },
        "deliveryCost": 0.0
      },
      "relationships": {
        "entries": {
          "links": {
            "self": "https://kaspi.kz/shop/api/v2/orders/NDk3MTQ6MDIx/relationships/entries",
            "related": "https://kaspi.kz/shop/api/v2/orders/NDk3MTQ6MDIx/entries"
          },
          "data": [
            {
              "type": "orderentries",
              "id": "NDk1MTQ1MDIxIyMw"
            },
            {
              "type": "orderentries",
              "id": "NDk0MTQ0MDIxIyMx"
            }
          ]
        },
        "user": {
          "links": {
            "self": "https://kaspi.kz/shop/api/v2/orders/NDk3MTQ6MDIx/relationships/user",
            "related": "https://kaspi.kz/shop/api/v2/orders/NDk3MTQ6MDIx/user"
          },
          "data": {
            "type": "customers",
            "id": "NzA3NjgyODAwNg"
          }
        }
      },
      "links": {
        "self": "https://kaspi.kz/shop/api/v2/orders/NDk3MTQ6MDIx"
      }
    }
  ],
  "included": [
    {
      "type": "orderentries",
      "id": "NDk0MTQ0MDIxIyMx",
      "attributes": {
        "unitType": "PIECES",
        "offer": {
          "code": "259204",
          "name": "Линейка"
        },
        "quantity": 1,
        "totalPrice": 1000.0,
        "weight": 0.0,
        "entryNumber": 1,
        "category": {
          "code": "Master - Rulers",
          "title": "Линейки"
        },
        "deliveryCost": 0.0,
        "basePrice": 1000.0,
        "isImeiRequired": false
      },
      "relationships": {
        "product": {
          "links": {
            "self": "https://kaspi.kz/shop/api/v2/orderentries/NDk0MTQ0MDIxIyMx/relationships/product",
            "related": "https://kaspi.kz/shop/api/v2/orderentries/NDk0MTQ0MDIxIyMx/product"
          },
          "data": {
            "type": "masterproducts",
            "id": "MTA5MzQ5MDI2"
          }
        },
        "deliveryPointOfService": {
          "links": {
            "self": "https://kaspi.kz/shop/api/v2/orderentries/NDk0MTQ0MDIxIyMx/relationships/deliveryPointOfService",
            "related": "https://kaspi.kz/shop/api/v2/orderentries/NDk0MTQ0MDIxIyMx/deliveryPointOfService"
          },
          "data": {
            "type": "pointofservices",
            "id": "VGVzdE1lcmNoYW00Ml0wMDAwNTY3OA"
          }
        }
      },
      "links": {
        "self": "https://kaspi.kz/shop/api/v2/orderentries/NDk0MTQ0MDIxIyMx"
      }
    }
  ],
  "meta": {
    "pageCount": 1,
    "totalCount": 1
  }
}


Parameters

page[number] – page number starting from zero. Required.

page[size] – number of results per page. Maximum value is 100. Required.

filter[orders][state] – order state. Required.

Enum values:

NEW – new order

SIGN_REQUIRED – order pending signing

PICKUP – pickup (also used for Kaspi Postomat orders)

DELIVERY – delivery

KASPI_DELIVERY – Kaspi Delivery, Kaspi Postomat

ARCHIVE – archived order

Signs of Kaspi Delivery:

"isKaspiDelivery": true

"deliveryMode": "DELIVERY_REGIONAL_TODOOR"

Signs of Kaspi Postomat:

"isKaspiDelivery": true

"deliveryMode": "DELIVERY_PICKUP"

filter[orders][status] – order statuses.

Enum values:

APPROVED_BY_BANK – approved by the bank

ACCEPTED_BY_MERCHANT – accepted for processing by the seller

COMPLETED – completed

CANCELLED – cancelled

CANCELLING – awaiting cancellation

RETURNED – returned

filter[orders][creationDate][$ge] – start date for order search, in milliseconds. Required.

filter[orders][creationDate][$le] – end date for order search, in milliseconds.
By default equals the current date. Maximum search period is 14 days.

filter[orders][deliveryType] – delivery method.
Enum values:

DELIVERY_PICKUP – pickup

DELIVERY_LOCAL – delivery

Important: this filter can be used only if the state filter is not equal to the given delivery method.

Attributes (fragment)

code – order code.

totalPrice – total order amount in tenge.

customer – customer who placed the order. Contains name, surname, and phone number.

deliveryMode – delivery method:

DELIVERY_LOCAL – delivery within the city;

DELIVERY_PICKUP – pickup (also used for Postomat orders);

DELIVERY_REGIONAL_TODOOR – regional delivery “to door”.

paymentMode – payment method:

PAY_WITH_CREDIT – purchase on credit;

PREPAID – non-cash payment.

signatureRequired – boolean, indicates whether document signing is required.

isKaspiDelivery – boolean, indicates whether the order is a Kaspi Delivery order.

creditTerm – credit/installment term.

preOrder – boolean, whether the order is a pre‑order.

state – order state (same values as the corresponding request parameter).

creationDate – order creation date in milliseconds.

approvedByBankDate – bank approval date in milliseconds.

plannedDeliveryDate – delivery date in milliseconds.

reservationDate – reservation date in milliseconds.

status – order status (same values as the corresponding request parameter).

deliveryCost – delivery cost.

waybill – link to the printed waybill for Kaspi Delivery orders.

courierTransmissionPlanningDate – planned date of transferring the order to the courier in milliseconds (Kaspi Delivery).

courierTransmissionDate – actual date of transferring the order to the courier in milliseconds (Kaspi Delivery).

latitude – geographic latitude.

longitude – geographic longitude.

waybillNumber – courier service waybill number.

category – product category.

deliveryCostForSeller – delivery commission.

apartment – apartment.

express – boolean, indicates whether the order is an Express Delivery order.

returnedToWarehouse – boolean, indicates whether the order has been returned to the warehouse.

Relationships

entries – order line items.

user – system user who placed the order.

Links

self – link to the order itself.
You can use it to retrieve that specific order.

2.2.2 Getting order contents by order code

Description

This request returns the contents of an order placed by customers.
It contains the total order price, delivery and payment types, status, state, and creation and bank approval dates.

Parameter

filter[orders][code] – order code. Required query parameter.

Relationships

deliveryPointOfService – point of sale.

product – product being sold.

Links

self – link that allows you to get a specific order line item.

Example for state PICKUP

Request

GET https://kaspi.kz/shop/api/v2/orders?filter[orders][code]=496149022&include[orders]=entries
Content-Type: application/vnd.api+json
X-Auth-Token: token


Response (same structure as in the list-of-orders example, with related orderentries in included).

Example for state KASPI_DELIVERY

Request

GET https://kaspi.kz/shop/api/v2/orders?filter[orders][code]=496149022&include[orders]=entries
Content-Type: application/vnd.api+json
X-Auth-Token: token


Response (fragment)

{
  "data": [
    {
      "id": "NTN7uzzgwOTk3",
      "type": "orders",
      "attributes": {
        "code": "496149022",
        "creationDate": 1745691162415,
        "totalPrice": 5990.0,
        "deliveryCostForSeller": 895.0,
        "isKaspiDelivery": true,
        "preOrder": false,
        "approvedByBankDate": 1745691163161,
        "signatureRequired": false,
        "status": "CANCELLING",
        "pickupPointId": "Merchant_00005678",
        "state": "KASPI_DELIVERY",
        "cancellationReason": "TIMEOUT_BUYER_PICKUP",
        "deliveryCost": 0.0,
        "customer": {
          "id": "NzAyMkIoMTE0MQ",
          "name": "Марат",
          "cellPhone": "7021234567",
          "firstName": "Марат",
          "lastName": "Маратов"
        },
        "originAddress": {
          "id": "U3VscGFrXzcyOTY",
          "displayName": "7296",
          "address": {
            "streetName": " улица Кунаева",
            "streetNumber": " 20",
            "town": "г. Талдыкорган",
            "district": null,
            "building": null,
            "apartment": null,
            "formattedAddress": "г. Талдыкорган, улица Кунаева, 20",
            "latitude": 44.9983024597168,
            "longitude": 78.36637115478516
          },
          "city": {
            "id": "MTkxMDEwMDAw",
            "code": "191010000",
            "name": "Талдыкорган",
            "active": true
          }
        },
        "kaspiDelivery": {
          "waybill": "https://kaspi.kz/shop/api/waybill/...",
          "courierTransmissionDate": 1745755274000,
          "courierTransmissionPlanningDate": 1745755274000,
          "waybillNumber": "101110589",
          "express": false,
          "returnedToWarehouse": false,
          "firstMileCourier": null
        },
        "assembled": true,
        "deliveryMode": "DELIVERY_PICKUP",
        "paymentMode": "PREPAID"
      },
      "relationships": {
        "entries": {
          "data": [
            {
              "id": "NTN7uzzgwOTk3IyMw",
              "type": "orderentries"
            }
          ],
          "links": {
            "self": "https://kaspi.kz/shop/api/v2/orders/NTN7uzzgwOTk3/relationships/entries",
            "related": "https://kaspi.kz/shop/api/v2/orders/NTN7uzzgwOTk3/entries"
          }
        },
        "user": {
          "data": {
            "id": "NzAyХхХхХTE0MQ",
            "type": "customers"
          },
          "links": {
            "self": "https://kaspi.kz/shop/api/v2/orders/NTN7uzzgwOTk3/relationships/user",
            "related": "https://kaspi.kz/shop/api/v2/orders/NTN7uzzgwOTk3/user"
          }
        }
      },
      "links": {
        "self": "https://kaspi.kz/shop/api/v2/orders/NTN7uzzgwOTk3"
      }
    }
  ],
  "included": [
    {
      "id": "NTN7uzzgwOTk3IyMw",
      "type": "orderentries",
      "attributes": {
        "entryNumber": 0,
        "deliveryCost": 0.0,
        "quantity": 1,
        "weight": 0.0,
        "basePrice": 5990.0,
        "totalPrice": 5990.0,
        "unitType": "PIECES",
        "category": {
          "code": "Master - Lids",
          "title": "Крышки для посуды"
        },
        "offer": {
          "code": "355654asiuowl",
          "isImeiRequired": false,
          "name": "Крышка Tefal St-Pet Glass lid 28 см (040 90 128)"
        }
      },
      "relationships": {
        "product": {
          "data": {
            "id": "MTDwTCc5MTg1",
            "type": "masterproducts"
          },
          "links": {
            "self": "https://kaspi.kz/shop/api/v2/orderentries/NTN7uzzgwOTk3IyMw/relationships/product",
            "related": "https://kaspi.kz/shop/api/v2/orderentries/NTN7uzzgwOTk3IyMw/product"
          }
        },
        "deliveryPointOfService": {
          "data": {
            "id": "U3VaseGFrXzscTY",
            "type": "pointofservices"
          },
          "links": {
            "self": "https://kaspi.kz/shop/api/v2/orderentries/NTN7uzzgwOTk3IyMwIyMw/relationships/deliveryPointOfService",
            "related": "https://kaspi.kz/shop/api/v2/orderentries/NTN7uzzgwOTk3IyMwIyMw/deliveryPointOfService"
          }
        }
      },
      "links": {
        "self": "https://kaspi.kz/shop/api/v2/orderentries/NTN7uzzgwOTk3IyMwIyMw"
      }
    }
  ],
  "meta": {
    "pageCount": 1,
    "totalCount": 1
  }
}

2.2.3 Getting a product from an order line item

Description

This request returns the product for a specific order line item.
It contains the product code, name, and manufacturer.

Parameter

orderEntryId – identifier of the order line item. Required path parameter.

Attributes

code – product code.

name – product name.

manufacturer – product manufacturer.

category – category name.

Link

self – link to the product itself. You can use it to retrieve that specific product.

Request

GET https://kaspi.kz/shop/api/v2/orderentries/MTAwMDEwMA==/product
Content-Type: application/vnd.api+json
X-Auth-Token: token


Response

{
  "data": {
    "id": "MTDwTCc5MTg1==",
    "type": "masterproducts",
    "attributes": {
      "code": "12705127",
      "name": "Tunga Zodiak 2 195/65 R15 95T",
      "category": "Шины для легковых и внедорожных автомобилей"
    },
    "relationships": {
      "merchantProduct": {
        "data": null,
        "links": {
          "self": "https://kaspi.kz/shop/api/v2/masterproducts/MTDwTCc5MTg1=/relationships/merchantProduct",
          "related": "https://kaspi.kz/shop/api/v2/masterproducts/MTDwTCc5MTg1=/merchantProduct"
        }
      }
    },
    "links": {
      "self": "https://kaspi.kz/shop/api/v2/masterproducts/MTDwTCc5MTg1="
    }
  },
  "included": []
}

2.3 Changing order status
2.3.1 General method for changing order status

Description

This request changes the status of an order.

Parameters

type – object type. Must be orders. Required.

id – object identifier (order ID). Required.

Attributes

code – order code. Optional.

status – new order status. Required.

May take one of the following values:

ACCEPTED_BY_MERCHANT — the order is accepted by the seller.
Can be used only if the current status is APPROVED_BY_BANK.

COMPLETED — the order has been issued to the customer.
Can be used only if the current status is ACCEPTED_BY_MERCHANT.

CANCELLED — the order is cancelled.
Can be used only if the current status is ACCEPTED_BY_MERCHANT or APPROVED_BY_BANK.

ARRIVED — the product has arrived at the regional point of sale.
Can be used only for pre‑order items and when the current status is ACCEPTED_BY_MERCHANT.

ASSEMBLE — the order is assembled.
Can be used only if the current status is ACCEPTED_BY_MERCHANT and the order is waiting to be handed over to the courier.

cancellationReason – cancellation reason. Required only when the status is CANCELLED.

Values:

BUYER_NOT_REACHABLE – unable to reach the customer by phone (for orders with seller delivery, state DELIVERY).

MERCHANT_OUT_OF_STOCK – out of stock.

cancellationComment – comment when cancelling an order.
May be set only when the status is CANCELLED.
Must not exceed 1000 characters.

Response

The response must return the object with the successfully updated status.

2.3.2 Confirming an order (status ACCEPTED_BY_MERCHANT)

Description

This request changes the order status to Accepted.

Parameters

type – object type. orders. Required.

id – object identifier. Required.

Attributes

code – order code. Optional.

status – required.
Set to ACCEPTED_BY_MERCHANT.
Can be used only if the current status is APPROVED_BY_BANK.

Request

https://kaspi.kz/shop/api/v2/orders
POST /api/v2/orders
HTTP/1.1
Host: kaspi.kz/shop
Content-Type: application/vnd.api+json
X-Auth-Token: token

{
  "data": {
    "type": "orders",
    "id": "NTN7uzzgwOTk3",
    "attributes": {
      "code": "543036631",
      "status": "ACCEPTED_BY_MERCHANT"
    }
  }
}


Response

{
  "data": {
    "type": "orders",
    "id": "NTN7uzzgwOTk3",
    "attributes": {
      "code": "543036631",
      "status": "ACCEPTED_BY_MERCHANT"
    },
    "relationships": {
      "entries": {
        "links": {
          "self": "https://kaspi.kz/shop/api/v2/orders/NTN7uzzgwOTk3/relationships/entries",
          "related": "https://kaspi.kz/shop/api/v2/orders/NTN7uzzgwOTk3/entries"
        }
      },
      "user": {
        "links": {
          "self": "https://kaspi.kz/shop/api/v2/orders/NTN7uzzgwOTk3/relationships/user",
          "related": "https://kaspi.kz/shop/api/v2/orders/NTN7uzzgwOTk3/user"
        },
        "data": null
      }
    },
    "links": {
      "self": "https://kaspi.kz/shop/api/v2/orders/NTN7uzzgwOTk3"
    }
  },
  "included": []
}

2.3.3 Completing an order (status COMPLETED)

Description

This request changes the order status to Completed / Issued.

Headers

X-Security-Code – secret code that was sent to the client.

X-Send-Code – always true.

Parameters

type – object type. orders. Required.

id – object identifier. Required.

Attributes

code – order code. Optional.

status – required.
For completing an order, set to COMPLETED.

Process:

First request — send COMPLETED with an empty X-Security-Code header.
The client will receive a push notification with a confirmation code in the Kaspi.kz mobile app.

After the customer provides the code, send a second request with the X-Security-Code header set to the code received from the client.

Request

https://kaspi.kz/shop/api/v2/orders
POST /api/v2/orders
HTTP/1.1
Host: kaspi.kz/shop
Content-Type: application/vnd.api+json
X-Auth-Token: token
X-Security-Code: 1234
X-Send-Code: true

{
  "data": {
    "type": "orders",
    "id": "MjAwNTcwMDN=",
    "attributes": {
      "code": "50049000",
      "status": "COMPLETED"
    }
  }
}


Response

{
  "data": {
    "type": "orders",
    "id": "MjAwNTcwMDN=",
    "attributes": {
      "code": "50049000",
      "status": "COMPLETED"
    },
    "relationships": {
      "entries": {
        "links": {
          "self": "/v2/orders/MjAwNTcwMDN=/relationships/entries",
          "related": "/v2/orders/MjAwNTcwMDN=/entries"
        }
      }
    }
  }
}


Possible errors when completing an order

Completion with incorrect confirmation code

{
  "errors": [
    {
      "title": "Security code is not valid. And the order cannot be completed without it"
    }
  ]
}


Completion when the order is already cancelled

{
  "errors": [
    {
      "title": "Order is cancelled, so it can't be completed."
    }
  ]
}


Completion when the order is already completed

{
  "errors": [
    {
      "title": "Order already has been completed, so it can't be completed again."
    }
  ]
}


Completion when the order still requires document signing by the client

{
  "errors": [
    {
      "title": "Order is not may complete allowed"
    }
  ]
}

2.4 Kaspi Delivery orders (Kaspi Доставка)
2.4.1 Assembling a Kaspi Delivery order

Description

This request changes the order status to Assembled.

Available only for orders with state KASPI_DELIVERY.

Parameters

type – object type. orders. Required.

id – object identifier. Required.

Attributes

code – order code. Optional.

status – required. Set to ASSEMBLE.

numberOfSpace – number of packages (places). Required.

Request

https://kaspi.kz/shop/api/v2/orders
POST /api/v2/orders
HTTP/1.1
Host: kaspi.kz/shop
Content-Type: application/vnd.api+json
X-Auth-Token: token

{
  "data": {
    "type": "orders",
    "id": "MjAwNTcwMDM=",
    "attributes": {
      "status": "ASSEMBLE",
      "numberOfSpace": "2"
    }
  }
}


Response (example)

{
  "data": {
    "type": "orders",
    "id": "MjAwNTcwMDM=",
    "attributes": {
      "code": "50049002",
      "status": "ASSEMBLED"
    },
    "relationships": {
      "entries": {
        "links": {
          "self": "/v2/orders/MjAwNTcwMDM=/relationships/entries",
          "related": "/v2/orders/MjAwNTcwMDM=/entries"
        }
      }
    }
  }
}

2.4.2 Cancelling a Kaspi Delivery order

Description

This request changes the order status to Cancelled.

Parameters

type – object type. orders. Required.

id – object identifier. Required.

Attributes

code – order code. Optional.

status – required. Set to CANCELLED.
Can be used only if the current status is ACCEPTED_BY_MERCHANT or APPROVED_BY_BANK.

cancellationReason – reason for cancellation. Required only when status is CANCELLED.

Possible values:

BUYER_NOT_REACHABLE – unable to reach the customer (available only for orders in state PICKUP).

MERCHANT_OUT_OF_STOCK – out of stock.

cancellationComment – comment when cancelling the order.
May be set only when status is CANCELLED. Must not exceed 1000 characters.

Request

https://kaspi.kz/shop/api/v2/orders
POST /api/v2/orders
HTTP/1.1
Host: kaspi.kz/shop
Content-Type: application/vnd.api+json
X-Auth-Token: token

{
  "data": {
    "type": "orders",
    "id": "MjAwNTcwDFM=",
    "attributes": {
      "code": "41249002",
      "status": "CANCELLED",
      "cancellationReason": "BUYER_CANCELLATION_BY_MERCHANT"
    }
  }
}


Response

{
  "data": {
    "type": "orders",
    "id": "MjAwNTcwDFM=",
    "attributes": {
      "code": "41249002",
      "status": "CANCELLED",
      "cancellationReason": "BUYER_CANCELLATION_BY_MERCHANT"
    },
    "relationships": {
      "entries": {
        "links": {
          "self": "/v2/orders/MjAwNTcwDFM=/relationships/entries",
          "related": "/v2/orders/MjAwNTcwDFM=/entries"
        }
      }
    }
  }
}

2.5 Partial cancellation of orders
2.5.1 Partial cancellation of a single item (orderEntryCancelOperation)

Description

This request allows you to reduce the quantity of a product in an order:

reduce the quantity if one line item has quantity ≥ 2; or

completely remove a specific product from an order that contains several different products.

Parameters

type – object type. orderEntryCancelOperation. Required.

Attributes

notes – comment for a partial cancellation. Optional.

remainedQuantity – remaining quantity of the product in the order.

Example: if the order has quantity 5 and you send 1, then 4 will be cancelled.
If you send 0, the product will be fully cancelled from the order.

id – identifier of the object (product). Required.

reason – reason for partial cancellation.

Possible values:

BUYER_NOT_REACHABLE – unable to reach the customer (available only for orders in state PICKUP).

MERCHANT_OUT_OF_STOCK – out of stock.

Request

https://kaspi.kz/shop/api/v2/orderEntryCancelOperation
POST /api/v2/orders
HTTP/1.1
Host: kaspi.kz/shop
Content-Type: application/vnd.api+json
X-Auth-Token: token

{
  "data": {
    "type": "orderEntryCancelOperation",
    "attributes": {
      "notes": "Отказ клиента",
      "remainedQuantity": 1,
      "reason": "BUYER_CANCELLATION_BY_MERCHANT"
    },
    "relationships": {
      "entry": {
        "data": {
          "type": "orderentries",
          "id": "MTcxODg0ODMxIyMx"
        }
      }
    }
  }
}


Response

{
  "data": {
    "type": "orderEntryCancelOperation",
    "id": "MTQ4NzEwNjU0MTE7MzA",
    "attributes": {
      "remainedQuantity": 1,
      "status": "SUCCESSFULL"
    },
    "relationships": {
      "entry": {
        "links": {
          "self": "https://kaspi.kz/shop/api/v2/orderEntryCancelOperation/MTQ4NzEwNjU0MTE7MzA/relationships/entry",
          "related": "https://kaspi.kz/shop/api/v2/orderEntryCancelOperation/MTQ4NzEwNjU0MTE7MzA/entry"
        },
        "data": null
      }
    },
    "links": {
      "self": "https://kaspi.kz/shop/api/v2/orderEntryCancelOperation/MTQ4NzEwNjU0MTE7MzA"
    }
  },
  "included": []
}

2.5.2 Bulk partial cancellation of several items

Description

This request allows you to decrease the quantity in an order for several products at once.

Parameters

type – object type. orderEntryCancelOperation. Required.

Attributes

notes – comment for partial cancellation. Optional.

remainedQuantity – remaining quantity of the product in the order.

If the order had quantity 5 and you send 1, then 4 will be cancelled.
If you send 0, the product will be fully cancelled.

remainedWeight – remaining weight.

By default must be a positive value (> 1).
If you send 0, the product will be fully cancelled in the order.

id – identifier of the product / order entry. Required.

reason – reason for partial cancellation.

Possible values:

BUYER_NOT_REACHABLE – unable to reach the customer (available only for orders in state PICKUP).

MERCHANT_OUT_OF_STOCK – out of stock.

Request

request PUT
https://kaspi.kz/shop/api/orderPartialCancel/NDQ0MjE0MDM4
header 'X-Auth-Token: <token>'
header 'Content-Type: application/vnd.api+json'

[
  {
    "entry": {
      "id": "NDQ0MjE0MDM4IyMw"
    },
    "remainedQuantity": 1,
    "remainedWeight": 1000,
    "reason": "MERCHANT_OUT_OF_STOCK",
    "notes": "merchant out of stock"
  },
  {
    "entry": {
      "id": "NDQ0MjE0MDM4IyMx"
    },
    "remainedQuantity": 1,
    "remainedWeight": 1000,
    "reason": "MERCHANT_OUT_OF_STOCK",
    "notes": "merchant out of stock"
  }
]


Response

{
  "orderCancelEntries": [
    {
      "id": "NDg5API4Nzk6JzAzMTg",
      "notes": "merchant out of stock",
      "entry": {
        "id": "NTQzLBL2LjMxIyMw"
      },
      "remainedQuantity": 1,
      "remainedWeight": 0.0
    }
  ],
  "status": "INPROGRESS"
}

2.5.3 Partial cancellation by weight

Description

The seller sends all changes (weight, quantity) for the order in a single request, and the system recalculates the item prices based on the new data.

If you send 0 as quantity or weight, the product will be completely removed from the order.

Parameters

remainedQuantity – remaining quantity of the product in the order.

remainedWeight – new product weight in grams.

reason – PRODUCT_UNDERWEIGHT – reason for partial cancellation “Product under‑weight”.

MDAwOTIwMDA – example order ID.

Attributes

unitType – product type:

"unitType": "MEASURABLE_PIECES" – solid-weight product;

"unitType": "MEASURABLE" – weight-based product;

"unitType": "PIECES" – piece product.

Example fragment of order entry

{
  "data": [
    {
      "type": "orderentries",
      "id": "NTAwMDA0MDAwMiMjMQ",
      "attributes": {
        "unitType": "MEASURABLE_PIECES",
        "quantity": 1,
        "totalPrice": 1000.0,
        "weight": 500.0,
        "entryNumber": 1,
        "deliveryCost": 0.0,
        "basePrice": 1000.0
      }
    }
  ]
}


Request

request PUT
url: https://kaspi.kz/shop/api/orderPartialCancel/MDAwOTIwMDA
Content-Type: application/vnd.api+json
X-Auth-Token: token

[
  {
    "entry": {
      "id": "MDAwOTQwMDEjIzA"
    },
    "remainedWeight": 280,
    "remainedQuantity": 1,
    "reason": "PRODUCT_UNDERWEIGHT",
    "notes": "Недовес по товару"
  },
  {
    "entry": {
      "id": "MDAwOTQwMDEjIzI"
    },
    "remainedWeight": 3900,
    "remainedQuantity": 9,
    "reason": "PRODUCT_UNDERWEIGHT",
    "notes": "Недовес по товару"
  },
  {
    "entry": {
      "id": "MDAwOTQwMDEjIzE"
    },
    "remainedWeight": 2200,
    "remainedQuantity": 3,
    "reason": "PRODUCT_UNDERWEIGHT",
    "notes": "Недовес по товару"
  }
]


Response

{
  "orderCancelEntries": [
    {
      "id": "ODc5NjIyNDIyNTMyNg",
      "entry": {
        "id": "MDAwOTQwMDEjIzA"
      },
      "remainedQuantity": 1,
      "remainedWeight": 280.0,
      "reason": "PRODUCT_UNDERWEIGHT",
      "notes": "Недовес по товару"
    },
    {
      "id": "ODc5NjIyNDI1ODA5NA",
      "entry": {
        "id": "MDAwOTQwMDEjIzI"
      },
      "remainedQuantity": 9,
      "remainedWeight": 3900.0,
      "reason": "PRODUCT_UNDERWEIGHT",
      "notes": "Недовес по товару"
    },
    {
      "id": "ODc5NjIyNDI5MDg2Mg",
      "entry": {
        "id": "MDAwOTQwMDEjIzE"
      },
      "remainedQuantity": 3,
      "remainedWeight": 2200.0,
      "reason": "PRODUCT_UNDERWEIGHT",
      "notes": "Недовес по товару"
    }
  ],
  "status": "SUCCESSFUL"
}

3. Working with orders via Kaspi Shop API (how‑to scenarios)

Below are practical “how‑to” instructions (FAQ style) that complement the formal Orders API specification.

3.1 How to change an order status via the API in Kaspi Shop?

To change an order status, send an API request.
You can use any service (Postman, Insomnia, Paw, Swagger, SoapUI) or integrate this with your accounting system.

Parameters

type – object type.
In this request: orders.

id – unique order ID.

To get it:

use the API in Kaspi Shop to get order details;

copy the id attribute value for "type": "orders".

Attributes

code – order number.

To get it:

use the API in Kaspi Shop to get a list of orders;

copy the code attribute value.

status – order status:

ACCEPTED_BY_MERCHANT – Accepted by the seller.

COMPLETED – Issued to the customer.

CANCELLED – Cancelled (for orders with status ACCEPTED_BY_MERCHANT or APPROVED_BY_BANK).

ARRIVED – Arrived at the warehouse (for pre‑order items).

ARRIVED_BACKWARD – Returned product arrived at the warehouse (for orders with status CANCELLING or KASPI_DELIVERY_RETURN_REQUESTED).

ASSEMBLE – Assembled (for orders with status ACCEPTED_BY_MERCHANT).

cancellationReason – cancellation reason.
Required when status is CANCELLED.

BUYER_CANCELLATION_BY_MERCHANT – the buyer cancelled the order.

BUYER_NOT_REACHABLE – unable to reach the customer.

MERCHANT_OUT_OF_STOCK – out of stock.

cancellationComment – seller’s comment.
For orders with status CANCELLING. Maximum 1000 characters.

Example request

https://kaspi.kz/shop/api/v2/orders
POST /api/v2/orders
HTTP/1.1
Host: kaspi.kz/shop
Content-Type: application/vnd.api+json
X-Auth-Token: token

{
  "data": {
    "type": "orders",
    "id": "ordersID=",
    "attributes": {
      "code": "ordercode",
      "status": "ARRIVED"
    }
  }
}


Example response

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

3.2 How to generate a waybill for Kaspi Delivery via the API?

To generate a waybill for handing an order over to Kaspi Delivery, change the order status to “Assembled”.
To do this, send an API request.
You can use any service (Postman, Insomnia, Paw, Swagger, SoapUI) or integration.

Parameters

type – object type.
In this request: orders.

id – unique order ID.

To get it:

use the API in Kaspi Shop to retrieve order details;

copy the id attribute value for "type": "orders".

Attributes

numberOfSpace – number of waybills (packages).
Set manually.

status – order status.
In this request: ASSEMBLE.

Example request

https://kaspi.kz/shop/api/v2/orders
POST /api/v2/orders
HTTP/1.1
Host: kaspi.kz/shop
Content-Type: application/vnd.api+json
X-Auth-Token: token

{
  "data": {
    "type": "orders",
    "id": "ordersID",
    "attributes": {
      "status": "ASSEMBLE",
      "numberOfSpace": "2"
    }
  }
}


Example response

{
  "data": {
    "type": "orders",
    "id": "ordersID=",
    "attributes": {
      "numberOfSpace": 2,
      "status": "ASSEMBLE"
    },
    "relationships": {
      "user": {
        "links": {
          "self": "https://kaspi.kz/shop/api/v2/orders/ordersID=/relationships/user",
          "related": "https://kaspi.kz/shop/api/v2/orders/ordersID=/user"
        },
        "data": null
      },
      "entries": {
        "links": {
          "self": "https://kaspi.kz/shop/api/v2/orders/ordersID=/relationships/entries",
          "related": "https://kaspi.kz/shop/api/v2/orders/ordersID=/entries"
        }
      }
    },
    "links": {
      "self": "https://kaspi.kz/shop/api/v2/orders/ordersID="
    }
  },
  "included": []
}

3.3 How to accept a new order via the API in Kaspi Shop?

To accept a new order, send an API request.

You can use any service (Postman, Insomnia, Paw, Swagger, SoapUI) or your accounting system.

Parameters

type – object type.
In this request: orders.

id – unique order ID.

To get it:

use the API in Kaspi Shop to get order details;

copy the id attribute value for "type": "orders".

Attributes

code – order number.

To get it:

use the API in Kaspi Shop to get a list of orders;

copy the code attribute value.

status – order status.
In this request: ACCEPTED_BY_MERCHANT.

Example request

https://kaspi.kz/shop/api/v2/orders
POST /api/v2/orders
HTTP/1.1
Host: kaspi.kz/shop
Content-Type: application/vnd.api+json
X-Auth-Token: token

{
  "data": {
    "type": "orders",
    "id": "ordersID",
    "attributes": {
      "code": "ordercode",
      "status": "ACCEPTED_BY_MERCHANT"
    }
  }
}


Example response

{
  "data": {
    "type": "orders",
    "id": "ordersID",
    "attributes": {
      "code": "ordercode",
      "status": "ACCEPTED_BY_MERCHANT"
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

3.4 How to change an order status to “Completed / Issued” via the API?

To change an order status to “COMPLETED” (Issued), send an API request.

You can use any service or your accounting system.

Parameters

X-Security-Code – code sent to the client in the Kaspi.kz mobile app.

X-Send-Code – status of sending the code.
In this request: true.

type – object type.
In this case: orders.

id – unique order ID.

To get it:

use the API in Kaspi Shop to get order details;

copy the id attribute value for "type": "orders".

Attributes

code – order number.

status – status to assign to the order.
In this request: COMPLETED.

Step 1. Leave the X-Security-Code parameter empty.
This is necessary so that the client receives the code in the Kaspi.kz mobile app.

Example of the first request — sending the code to the customer

https://kaspi.kz/shop/api/v2/orders
POST /api/v2/orders
HTTP/1.1
Host: kaspi.kz/shop
Content-Type: application/vnd.api+json
X-Auth-Token: token
X-Security-Code:
X-Send-Code: true

{
  "data": {
    "type": "orders",
    "id": "ordersID",
    "attributes": {
      "code": "ordercode",
      "status": "COMPLETED"
    }
  }
}


Step 2. Send a repeat request.
Insert the code provided by the client into the X-Security-Code parameter.

Example of the second request — completing the order

https://kaspi.kz/shop/api/v2/orders
POST /api/v2/orders
HTTP/1.1
Host: kaspi.kz/shop
Content-Type: application/vnd.api+json
X-Auth-Token: token
X-Security-Code: 1234
X-Send-Code: true

{
  "data": {
    "type": "orders",
    "id": "ordersId",
    "attributes": {
      "code": "ordercode",
      "status": "COMPLETED"
    }
  }
}


Example response

{
  "data": {
    "type": "orders",
    "id": "ordersID",
    "attributes": {
      "code": "ordercode",
      "status": "COMPLETED"
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

3.5 How to cancel an order via the API in Kaspi Shop?

To cancel an order, send an API request.

You can use any service or your accounting system.

Parameters

type – request target.
In this case: orders.

id – unique order ID.

To get it:

use the API in Kaspi Shop to get order details;

copy the id value for "type": "orders".

Attributes

code – order number.

To get it:

use the API in Kaspi Shop to get a list of orders;

copy the code attribute.

status – status to set for the order.

CANCELLED – cancelled.
Use if the current status is ACCEPTED_BY_MERCHANT.

cancellationReason – cancellation reason.

BUYER_CANCELLATION_BY_MERCHANT – customer refused.

BUYER_NOT_REACHABLE – unable to reach the customer.

MERCHANT_OUT_OF_STOCK – out of stock.

cancellationComment – comment when cancelling the order.
Must not exceed 1000 characters.

Example request

https://kaspi.kz/shop/api/v2/orders
POST /api/v2/orders
HTTP/1.1
Host: kaspi.kz/shop
Content-Type: application/vnd.api+json
X-Auth-Token: token

{
  "data": {
    "type": "orders",
    "id": "ordersID",
    "attributes": {
      "code": "ordercode",
      "status": "CANCELLED",
      "cancellationReason": "BUYER_CANCELLATION_BY_MERCHANT"
    }
  }
}


Example response

{
  "data": {
    "type": "orders",
    "id": "ordersID",
    "attributes": {
      "cancellationReason": "BUYER_CANCELLATION_BY_MERCHANT",
      "status": "CANCELLED"
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

3.6 How to change the weight of products in an order via the API?

To change the weight of products in an order, send an API request.

You can use any service or your accounting system.

Parameters

remainedWeight – how much the product weighs.

If you set 0, the product will be removed from the order.

remainedQuantity – how many units of the product should remain in the order.

reason – reason for the changes.

PRODUCT_UNDERWEIGHT – product under‑weight.

notes – seller’s comment on the changes.

id – unique order line item ID.

To get it:

use the API in Kaspi Shop to get information about products in the order;

copy the id attribute value for "type": "orderentries".

Example request

request PUT
url: https://kaspi.kz/shop/api/orderPartialCancel/MDAwOTIwMDA
Content-Type: application/vnd.api+json
X-Auth-Token: token

[
  {
    "entry": {
      "id": "orderentriesId"
    },
    "remainedWeight": 1000,
    "remainedQuantity": 1,
    "reason": "PRODUCT_UNDERWEIGHT",
    "notes": "Недовес по товару"
  }
]


The response will contain updated information about product quantities and weights in the order.

Response parameters

remainedQuantity – how many units of the product must remain in the order.

remainedWeight – how much the product weighs.

If you set 0, the product will be removed from the order.

reason – reason for the changes.
PRODUCT_UNDERWEIGHT – product under‑weight.

notes – seller’s comment.

id – unique order line item ID.

Example response

{
  "orderCancelEntries": [
    {
      "id": "Mjc0ODI0MzEwMjkyOTQ",
      "notes": "Недовес по товару",
      "entry": {
        "id": "orderentriesId"
      },
      "remainedQuantity": 1,
      "remainedWeight": 1000.0
    }
  ],
  "status": "INPROGRESS"
}

3.7 How to delete some products from an order via the API?

To delete some products from an order, send an API request.

You can use any service or your accounting system.

Parameters

type – request target.
In this case: orderEntryCancelOperation.

Attributes

notes – comment for the cancellation.

remainedWeight – how much the order now weighs.

Information will be provided in the API response.

remainedQuantity – how many products will remain in the order.

Example: if there were 10 products and you cancel 2, the value is 8.

id – unique product ID.

To get it:

use the API in Kaspi Shop to get information about products in the order;

copy the id attribute value for "type": "orderentries".

reason – reason for cancellation.

BUYER_CANCELLATION_BY_MERCHANT – customer refused.

BUYER_NOT_REACHABLE – unable to reach the customer.

MERCHANT_OUT_OF_STOCK – out of stock.

Example request

https://kaspi.kz/shop/api/v2/orderEntryCancelOperation
POST /api/v2/orders
HTTP/1.1
Host: kaspi.kz/shop
Content-Type: application/vnd.api+json
X-Auth-Token: token

{
  "data": {
    "type": "orderEntryCancelOperation",
    "attributes": {
      "notes": "Отказ клиента",
      "remainedQuantity": 1,
      "reason": "BUYER_CANCELLATION_BY_MERCHANT"
    },
    "relationships": {
      "entry": {
        "data": {
          "type": "orderentries",
          "id": "orderentriesID"
        }
      }
    }
  }
}


Example response

{
  "data": {
    "type": "orderEntryCancelOperation",
    "id": "orderEntryCancelOperationID",
    "attributes": {
      "remainedWeight": 0.0,
      "remainedQuantity": 0,
      "status": "INPROGRESS"
    },
    "relationships": {
      "entry": {
        "links": {
          "self": "https://kaspi.kz/shop/api/v2/orderEntryCancelOperation/orderEntryCancelOperationID/relationships/entry",
          "related": "https://kaspi.kz/shop/api/v2/orderEntryCancelOperation/orderEntryCancelOperationID/entry"
        },
        "data": null
      }
    },
    "links": {
      "self": "https://kaspi.kz/shop/api/v2/orderEntryCancelOperation/orderEntryCancelOperationID"
    }
  },
  "included": []
}

3.8 How to get information about products in an order via the API?

To get information about products in an order, send an API request.

You can use any service or your accounting system.

Parameter

orderId – unique order ID.

To get it:

use the API in Kaspi Shop to get order details;

copy the id attribute value for "type": "orders".

Example request

GET https://kaspi.kz/shop/api/v2/orders/orderID/entries
Content-Type: application/vnd.api+json
X-Auth-Token: token


The response will contain information about the order cost, all products, and their quantities.

Attributes

id – unique product ID in the order.

unitType – product type:

MEASURABLE_PIECES – solid-weight product;

MEASURABLE – weight product;

PIECES – piece product.

quantity – quantity of each product in the order.

totalPrice – total order cost.

weight – product weight (only for products with a specified weight).

entryNumber – product number in the order.

category – category code and name.

deliveryCost – delivery cost.

basePrice – product price.

isImeiRequired – whether an IMEI code is required in the order:

true – IMEI must be specified;

false – IMEI is not required.

Example response

{
  "data": [
    {
      "type": "orderentries",
      "id": "orderentriesId",
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
    }
  ],
  "included": []
}

3.9 How to get descriptions of products in an order via the API?

To get descriptions of products in an order, send an API request.

You can use any service or your accounting system.

Parameter

orderentriesID – unique order line item ID.

To get it:

use the API in Kaspi Shop to get the order composition;

copy the id attribute for "type": "orderentries".

Example request

GET https://kaspi.kz/shop/api/v2/orderentries/orderentriesID/product
Content-Type: application/vnd.api+json
X-Auth-Token: token


The response will contain the product code in Kaspi Shop, name, brand, and category.

Attributes

id – unique order product ID.

code – product code in Kaspi Shop.

name – name.

manufacturer – brand.

category – category name.

Example response

{
  "data": {
    "type": "masterproducts",
    "id": "masterproductsId",
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

3.10 How to get information about a single product in an order via the API?

To get information about a single product in an order, send an API request.

You can use any service or your accounting system.

Parameter

orderentriesId – unique product ID in the order.

To get it:

use the API in Kaspi Shop to get information about products in the order;

copy the id attribute for "type": "orderentries".

Example request

GET https://kaspi.kz/shop/api/v2/orderentries/orderentriesId
Content-Type: application/vnd.api+json
X-Auth-Token: token


You will receive the cost of each product and how many units the client purchased.

Attributes

id – unique product ID in the order.

unitType – product type:

MEASURABLE_PIECES – solid-weight product;

MEASURABLE – weight product;

PIECES – piece product.

minAllowedWeight – minimum product weight.

quantity – quantity of each product in the order.

totalPrice – total order cost.

weight – product weight (for products with weight).

entryNumber – product number in the order.

category – category code and name.

deliveryCost – delivery cost.

basePrice – product price.

Example response

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

3.11 How to get the description of a single merchant product via the API?

To get the description of a single merchant product from an order, send an API request.

You can use any service or your accounting system.

Parameter

masterproductsID – unique master product ID.

To get it:

use the API in Kaspi Shop to get the product description from the order;

copy the id attribute for "type": "masterproducts".

Example request

GET https://kaspi.kz/shop/api/v2/masterproducts/masterproductsID/merchantProduct
Content-Type: application/vnd.api+json
X-Auth-Token: token


In the response you will receive the merchant product code, name, and brand.

Attributes

id – unique merchant product ID in the order.

code – merchant’s product code.

name – name.

manufacturer – brand.

Example response

{
  "data": {
    "type": "merchantproducts",
    "id": "merchantproductsID",
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

3.12 How to find a warehouse address via the API?

To find a warehouse address, send an API request.

You can use any service or your accounting system.

Parameter

pointOfServiceId – unique warehouse ID.

To get it:

use the API in Kaspi Shop to get information about the warehouse from which the customer ordered the product;

copy the id attribute for "type": "pointofservices".

Example request

GET https://kaspi.kz/shop/api/v2/pointofservices/pointofservicesId
Content-Type: application/vnd.api+json
X-Auth-Token: token


The response will contain the name and address of the warehouse.

Attributes

id – unique warehouse ID.

address – warehouse address:

streetName – street;

streetNumber – house number;

town – city;

district – district;

building – building number;

formattedAddress – full address;

latitude – latitude;

longitude – longitude.

displayName – warehouse name.

Example response

{
  "data": {
    "type": "pointofservices",
    "id": "pointofservicesId",
    "attributes": {
      "address": {
        "streetName": " улица Каныша Сатпаева",
        "streetNumber": " 22/1",
        "town": "г. Алматы",
        "district": null,
        "building": null,
        "apartment": null,
        "formattedAddress": "г. Алматы, улица Каныша Сатпаева, 22/1",
        "latitude": 43.23662559520485,
        "longitude": 76.93337309399296
      },
      "displayName": "PP1"
    },
    "relationships": {
      "city": {
        "links": {
          "self": "https://kaspi.kz/shop/api/v2/pointofservices/pointofservicesId/relationships/city",
          "related": "https://kaspi.kz/shop/api/v2/pointofservices/pointofservicesId/city"
        },
        "data": {
          "type": "cities",
          "id": "citiesID"
        }
      }
    },
    "links": {
      "self": "https://kaspi.kz/shop/api/v2/pointofservices/pointofservicesId"
    }
  },
  "included": []
}

3.13 How to find from which warehouse the customer ordered a product via the API?

To find out from which warehouse the customer ordered a product, send an API request.

You can use any service or your accounting system.

Parameter

orderentriesID – unique order line item ID.

To get it:

use the API in Kaspi Shop to get the order composition;

copy the id attribute for "type": "orderentries".

Example request

GET https://kaspi.kz/shop/api/v2/orderentries/orderentriesID/deliveryPointOfService
Content-Type: application/vnd.api+json
X-Auth-Token: token


The response will contain the name and address of the warehouse from which the customer ordered the product.

Attributes

id – unique warehouse ID.

address – warehouse address:

streetName – street;

streetNumber – house number;

town – city;

district – district;

building – building;

formattedAddress – full address;

latitude – latitude;

longitude – longitude.

displayName – warehouse code.

Example response

{
  "data": {
    "type": "pointofservices",
    "id": "pointofservicesId",
    "attributes": {
      "address": {
        "streetName": " улица Каныша Сатпаева",
        "streetNumber": " 22/1",
        "town": "г. Алматы",
        "district": null,
        "building": null,
        "apartment": null,
        "formattedAddress": "г. Алматы, улица Каныша Сатпаева, 22/1",
        "latitude": 43.23662559520485,
        "longitude": 76.93337309399296
      },
      "displayName": "PP1"
    },
    "relationships": {
      "city": {
        "links": {
          "self": "https://kaspi.kz/shop/api/v2/pointofservices/pointofservicesId/relationships/city",
          "related": "https://kaspi.kz/shop/api/v2/pointofservices/pointofservicesId/city"
        },
        "data": {
          "type": "cities",
          "id": "citiesID"
        }
      }
    },
    "links": {
      "self": "https://kaspi.kz/shop/api/v2/pointofservices/pointofservicesId"
    }
  },
  "included": []
}

4. Product import API in Kaspi Shop
4.1 How to add a product for sale in Kaspi Shop via the API?

To add a product for sale in Kaspi Shop, send an API request.

You can use any service (Postman, Insomnia, Paw, Swagger, SoapUI) or integrate this with your accounting system.

Parameters

sku – product SKU.

title – product name.

brand – brand.

category – category code.

To get it:

use the API in Kaspi Shop to get a list of categories;

copy the code attribute.

description – seller’s description.

images – product images.

Specify a link to the image in the url key.

Attribute list

code – product attribute code.

To get it:

use the API in Kaspi Shop to get a list of attributes for the category;

copy the code attribute.

value – attribute value.

Example request

POST /shop/api/products/import HTTP/1.1
Host: kaspi.kz
Accept: application/json
X-Auth-Token: token
Content-Type: text/plain

// body

[
  {
    "sku": "Testsku",
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


The response will contain the unique product upload code and the result of adding the product to Kaspi Shop.

Example response

{
  "code": "testproduct",
  "status": "UPLOADED"
}

4.2 How to get a list of product attributes via the API?

To get a list of product attributes, send an API request.

You can use any service or your accounting system.

Parameter

c – category code.

To get it:

use the API in Kaspi Shop to get a list of categories;

copy the code attribute.

Example request

GET https://kaspi.kz/shop/api/products/classification/attributes?c=Master - Exercise notebooks&HTTP/1.1=&Host=kaspi.kz
Accept: application/json
X-Auth-Token: token


The response will contain a list of attributes for each characteristic.
If you provide product data for those attributes, they will be displayed on the product card in Kaspi Shop.

Attributes

code – attribute code.

type – variable type allowed for the description:

boolean – only true or false;

enum – value from a list;

string – text;

number – number.

multiValued – whether multiple values can be specified:

true – yes;

false – no.

mandatory – whether the attribute is required:

true – required;

false – not required.

Example response (fragment)

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
  }
]

4.3 How to obtain the JSON schema for adding new products via the API?

To obtain the JSON schema for adding new products via the API, send an API request.

You can use any service or your accounting system.

Example request

GET https://kaspi.kz/shop/api/products/import/schema?HTTP/1.1=&Host=kaspi.kz
Accept: application/json
X-Auth-Token: token


The response will contain the parameters that can be used when working with the API in Kaspi Shop and a description of the data for each parameter.

Example response (fragment)

{
  "$schema": "http://json-schema.org/draft-04/schema#",
  "title": "Product attributes import scheme",
  "description": "Used to validate JSON documents with product attribute values and images.",
  "type": "array",
  "minItems": 1,
  "maxItems": 10000,
  "items": {
    "title": "Array of products",
    "description": "Contains individual products with their attributes and images.",
    "type": "object",
    "properties": {
      "sku": {
        "title": "SKU",
        "description": "Unique identifier used to find products in catalog.",
        "type": "string",
        "maxLength": 64,
        "minLength": 1,
        "example": "00167PVS"
      },
      "title": {
        "title": "Product title",
        "description": "Contains product title that would be shown on storefront, without category prefix (eg. Smartphone, Fridge etc.).",
        "type": "string",
        "maxLength": 1024,
        "minLength": 1,
        "example": "Sony Alpha A6100 Kit 16-50 мм OSS черный"
      },
      "brand": {
        "title": "Product brand",
        "description": "Contains product brand name that would be used in 'Brand' facet on product listing pages of storefront.",
        "type": "string",
        "maxLength": 256,
        "minLength": 1,
        "example": "Sony"
      },
      "category": {
        "title": "Category code",
        "description": "This code would be used to assign the product to a category. It also defines the scope of available attributes. Only leaf categories are accepted",
        "type": "string",
        "maxLength": 512,
        "minLength": 1,
        "example": "Master - Photo cameras",
        "pattern": "^Master ?-[a-zA-Z_\\s\\d-]+$"
      },
      "description": {
        "title": "Short product definition",
        "description": "Contains small product definition used on item page. Usually defaults to some major specs.",
        "type": "string",
        "maxLength": 1024,
        "minLength": 1,
        "example": "- тип: беззеркальная со сменной оптикой\n- число эффективных пикселов: 24 Мпикс\n- объектив в комплекте: да\n- диагональ жк-экрана: 3 дюйм\n- ручная настройка выдержки и диафрагмы: да"
      },
      "weight": {
        "title": "Product's weight (optional)",
        "description": "Contains double value, but type is string",
        "type": "string",
        "maxLength": 256,
        "minLength": 1
      },
      "attributes": {
        "title": "List of attributes",
        "description": "Array of attributes available for the assigned category.",
        "type": "array",
        "minItems": 1,
        "maxItems": 256
      },
      "images": {
        "title": "Product images",
        "description": "Must contain at least one valid image url. Valid means downloadable and having valid picture as content. Redirects are supported.",
        "type": "array",
        "minItems": 1,
        "uniqueItems": true
      }
    },
    "required": [
      "sku",
      "title",
      "brand",
      "category",
      "attributes",
      "images"
    ],
    "additionalProperties": false
  }
}

4.4 How to get possible values for product attributes via the API?

To get possible values for product attributes, send an API request.

You can use any service or your accounting system.

Parameters

c – product category code.

To get it:

use the API in Kaspi Shop to get a list of categories;

copy the code attribute.

a – attribute code.

To get it:

use the API in Kaspi Shop to get a list of attributes for the category;

copy the code attribute.

Example request

GET https://kaspi.kz/shop/api/products/classification/attribute/values?c=Master - Exercise notebooks&HTTP/1.1=&Host=kaspi.kz&a=Exercise notebooks*Obsie harakteristiki.exercise notebooks*cover
Accept: application/json
X-Auth-Token: token


The response will contain recommended values for the attribute.

Attributes

code – value code.

name – name.

Example response

[
  {
    "code": "мягкая",
    "name": "мягкая"
  },
  {
    "code": "твердая",
    "name": "твердая"
  }
]

4.5 How to get the category code for adding a product via the API?

To get a category code for adding a product, send an API request.

You can use any service or your accounting system.

Example request

GET /shop/api/products/classification/categories HTTP/1.1
Host: kaspi.kz
Accept: application/json
X-Auth-Token: token


The response will contain category names and their codes for API requests.

Attributes

code – category code for API requests.

title – category name in Kaspi Shop.

Example response

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

4.6 I added products for sale via the API. How to get the result?

To find out the result of product upload, send an API request.

You can use any service or your accounting system.

Parameter

i – product upload code.

Example request

GET https://kaspi.kz/shop/api/products/import/result?i=testproduct&HTTP/1.1=&Host=kaspi.kz
Accept: application/json
X-Auth-Token: token


The response will contain a detailed result of product validation.

Attributes

errors – number of products with errors.

warnings – number of products with warnings.

skipped – number of skipped products.

total – total number of uploaded products.

state / result – upload result.

Example response

{
  "errors": 0,
  "warnings": 0,
  "skipped": 0,
  "total": 1,
  "result": {
    "Testsku": {
      "state": "FINISHED"
    }
  }
}

4.7 How to check that a product is added for sale in Kaspi Shop via the API?

To check that a product is added for sale, send an API request.

You can use any service or your accounting system.

Parameter

i – product upload code.

To get it:

use the API in Kaspi Shop to add a product for sale;

copy the code attribute.

Example request

GET https://kaspi.kz/shop/api/products/import?i=testproduct&HTTP/1.1=&Host=kaspi.kz
Accept: application/json
X-Auth-Token: token


The response will show the processing status.

Attributes

code – product upload code.

status – processing status.

description – seller’s description.

Example response

{
  "code": "testproduct",
  "status": "FINISHED"
}