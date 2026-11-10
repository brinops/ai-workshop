# Перевірка інтеграцій для воркшопу

| Задача | Статус | Результат |
| --- | --- | --- |
| W01 · Slack і мережа | Частково зроблено | У живому Slack підтверджено локальний Socket Mode, прив’язку з DM, відкриття треду й отримання permalink. Живу відповідь у треді та натискання кнопки підтверджено. Маршрутизацію через приватну мережу перевірено інтеграційним тестом із двома локальними базами. Залишилась репетиція на двох фізичних ноутбуках. |
| W02 · Claude Code | Пройдено в локальному середовищі | Claude Code 2.1.319 із наявним входом через Claude.ai та моделлю Sonnet. Headless-прогін делегував роботу локальному `booking-investigator`, повернув `{"expected":"waitlist"}` і записав `SubagentStart` та `SubagentStop` з одним ID агента. Тривалість виклику близько 11 секунд. |
| W03 · Jira | Потрібен доступ | У доступній конфігурації немає підключення Jira. Потрібно підтвердити тип Jira, тестовий проєкт і акаунт із правами читання та зміни опису. Навчальна фікстура й локальне сховище можуть розроблятися незалежно. |

## Як повторити W02

У тимчасовому робочому каталозі створити `.claude/agents/booking-investigator.md` із полями `name: booking-investigator`, `description` і `tools: Read` у front matter. Інструкція агента має відповідати, що другий клієнт потрапляє в лист очікування. У `.claude/settings.json` налаштувати `SubagentStart` і `SubagentStop` з matcher `booking-investigator`. Для обох подій використати command hook `cat >> "$WORKSHOP_PROBE_DIR/hooks.jsonl"`. Перед запуском виконати `export WORKSHOP_PROBE_DIR="$PWD"`.

```sh
claude -p --setting-sources project --no-session-persistence \
  --permission-mode dontAsk --tools Agent,Read \
  --allowed-tools 'Agent(booking-investigator)' --max-turns 5 \
  --max-budget-usd 0.50 --model sonnet --output-format stream-json --verbose \
  --json-schema '{"type":"object","properties":{"expected":{"type":"string","enum":["waitlist"]}},"required":["expected"],"additionalProperties":false}' \
  'Delegate to the booking-investigator subagent using the Agent tool. Ask what should happen to the second customer when the final workshop seat is taken. Use the answer to return structured output.' \
  > stream.jsonl
```

У `stream.jsonl` має бути успішний результат зі структурованим значенням `{"expected":"waitlist"}`. У `hooks.jsonl` мають з’явитися дві події для одного subagent. Перевірка використовує окрему конфігурацію. Підключення hooks до штатного runner входить у W14 і W20.
