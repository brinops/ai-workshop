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
2. Виконай відповідну гілку в `Runbooks`. Зафіксуй результат перевірки для висновку Reviewer.
3. Зістав diff і результати перевірок із погодженими вимогами. Якщо є розбіжність, назви конкретний критерій приймання.

## Runbooks

### Static page

- IF: Маршрут у плані дорівнює `PAGE_ROUTE`.
- THEN: Виконай цю команду через Bash.

```bash
python3 -I .claude/skills/workshop-page-review/scripts/check_page.py
```

- IF: Bash відхилив команду через додані аргументи або іншу команду.
- THEN: Повтори дослівно команду з цього runbook.
- EXAMPLES:
  - `Static page checks passed.` і успішний статус Bash підтверджують, що скрипт пройшов. Далі перевір критерії плану за diff.
  - `Link the local styles.css file.` вказує, що сторінка не підключає локальну таблицю стилів.

### Other routes

- IF: Маршрут у плані відрізняється від `PAGE_ROUTE`.
- THEN: Використовуй вивід перевірок, який надав бекенд.
- EXAMPLES:
  - Для `booking-backend` використай результат тестів Python із вхідних даних Reviewer.
