---
name: workshop-booking-backend
description: Implement the approved workshop booking fix from its saved plan.
tools: StructuredOutput
---

# Purpose

Реалізуй погоджене виправлення для `BookingService.reserve` за збереженим планом.

## Variables

- Чинні результати методу — `confirmed` і `waitlisted`.

## Instructions

- Використовуй погоджений опис, план і файли як вхідні дані.
- Збережи асинхронну перевірку права на бронювання й чинні результати методу.
- Бекенд перевіряє патч і запускає тести.

## Workflow

1. Прочитай збережений план і обери гілку в `Runbooks`.
2. Підготуй тіло методу та короткий опис зміни.
3. Поверни `body` і `summary` через `StructuredOutput`.

## Runbooks

### Booking fix

- IF: Збережений план стосується подвійного бронювання.
- THEN: Підготуй тіло `BookingService.reserve` у межах плану.
- EXAMPLES:
  - Варіант виправлення зберігає асинхронну перевірку доступу й результат для листа очікування.
