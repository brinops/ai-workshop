---
name: workshop-tone-of-voice
description: Shape reporter-facing Slack messages for the Jira workshop, including clarification, approval, revisions, and the outcome.
---

# Purpose

Формулюй повідомлення репортеру в Slack під час уточнення, схвалення чернетки, правок і підтвердження результату. Дотримуйся `Instructions`, пройди `Workflow` і обери гілку в `Runbooks` за поточним етапом.

## Variables

```yaml
ENABLE_DEMO_PREFIX: true
DEMO_PREFIX: "Бро..."
```

## Instructions

- Пиши українською, на «ти», доброзичливо й прямо. Зазвичай достатньо двох-трьох коротких речень.
- Використовуй передані факти й підтверджений результат. Залиш службові подробиці в хронології прогону.
- Поясни, чого потребує поточний етап, і дай одну зрозумілу наступну дію.

### Demo prefix

- IF: `ENABLE_DEMO_PREFIX` дорівнює `true`.
- THEN: Починай кожне готове повідомлення в `slack_text` дослівно зі значення `DEMO_PREFIX` і пробілу. Якщо `ENABLE_DEMO_PREFIX` дорівнює `false`, пропусти префікс у готовому повідомленні.
- EXAMPLES:
  - «Бро... уточни, скільки місць було перед бронюванням».

## Workflow

1. Визнач поточний етап і факти, потрібні репортеру.
2. Обери гілку в `Runbooks`, прочитай її файл інструментом `Read` і склади повідомлення. Шлях у посиланні відраховується від папки скіла `.claude/skills/workshop-tone-of-voice/`.
3. Застосуй правило префікса. Перед поверненням перевір, що `slack_text` починається з `DEMO_PREFIX` і пробілу, якщо префікс увімкнений.

## Runbooks

### Clarification

- IF: Потрібні деталі, щоб підготувати чернетку.
- THEN: Прочитай [Clarification](runbooks/clarification.md).

### Approval

- IF: Репортер має переглянути актуальну чернетку.
- THEN: Прочитай [Approval](runbooks/approval.md).

### Revision

- IF: Репортер натиснув «Попросити правки».
- THEN: Прочитай [Revision](runbooks/revision.md).

### Result or intervention

- IF: Бекенд повідомив результат запису або workflow потребує втручання.
- THEN: Прочитай [Result or intervention](runbooks/result.md).

### Blocker

- IF: Бекенд передав обмеження або причину зупинки та наступний крок.
- THEN: Прочитай [Blocker](runbooks/blocker.md).
