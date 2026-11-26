---
name: workshop-page-review
description: Run the bundled offline structure check when reviewing the static-page workshop route.
---

# Purpose

Перевір статичну сторінку скриптом зі скіла та зістав diff із погодженими вимогами. Дотримуйся `Instructions`, пройди `Workflow` і обери гілку в `Runbooks` за маршрутом.

## Variables

```yaml
PAGE_ROUTE: "static-page"
PASS_MARKER: "Static page checks passed."
```

## Instructions

- Для `PAGE_ROUTE` запусти перевірку через Bash із кореня робочої папки.
- Передай Bash точну команду з runbook без префіксів, додаткових аргументів, перенаправлень чи інших команд.
- Успіх скрипта підтверджують успішний статус Bash і рядок `PASS_MARKER`.

## Workflow

1. Визнач маршрут зі збереженого плану.
2. Обери гілку в `Runbooks`, прочитай її файл через `Read` і виконай інструкції. Шлях у посиланні відраховується від папки скіла `.claude/skills/workshop-page-review/`.
3. Зістав diff і результати перевірок із погодженими вимогами. Якщо є розбіжність, назви конкретний критерій приймання.

## Runbooks

### Static page

- IF: Маршрут у плані дорівнює `PAGE_ROUTE`.
- THEN: Прочитай [Static page](runbooks/static-page.md) і виконай точну команду з файла.

### Other routes

- IF: Маршрут у плані відрізняється від `PAGE_ROUTE`.
- THEN: Використовуй вивід перевірок, який надав бекенд.
- EXAMPLES:
  - Для `booking-backend` використай результат тестів Python із вхідних даних Reviewer.
