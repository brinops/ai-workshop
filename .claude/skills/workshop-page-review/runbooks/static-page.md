# Static page

- IF: Маршрут у плані дорівнює `PAGE_ROUTE`.
- THEN: Виконай цю команду через Bash із кореня робочої папки.

```bash
python3 -I .claude/skills/workshop-page-review/scripts/check_page.py
```

- IF: Bash відхилив команду через додані аргументи або іншу команду.
- THEN: Повтори дослівно команду з цього runbook.
- EXAMPLES:
  - `Static page checks passed.` і успішний статус Bash підтверджують, що скрипт пройшов. Далі перевір критерії плану за diff.
  - `Link the local styles.css file.` вказує, що сторінка не підключає локальну таблицю стилів.
