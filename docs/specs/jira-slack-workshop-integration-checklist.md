# Чекліст живої інтеграції Slack і Jira для воркшопу

Для першої живої перевірки з одним учасником використовуємо **локальний Slack Socket Mode** і навчальну Jira. Бекенд приймає Slack-події вихідним WebSocket і публікує тред через Slack Web API. Розділи 1–3 нижче описують окремий варіант зі спільним HTTP-маршрутизатором.

## Локальний Socket Mode для одного учасника

1. У Slack App відкрий **Socket Mode → Enable Socket Mode**. Якщо застосунок просить створити токен, обери `connections:write`. Токен також можна створити в **Basic Information → App-Level Tokens → Generate Token and Scopes**. У **Event Subscriptions** залиш увімкненим `message.im` серед **Bot Events**. [Налаштування Socket Mode](https://docs.slack.dev/apis/events-api/using-socket-mode/)
2. У кореневий `.env` поруч із наявним `WORKSHOP_SLACK_BOT_TOKEN` додай `WORKSHOP_SLACK_APP_TOKEN=xapp-…`. Залиши наявні `WORKSHOP_SLACK_WORKSPACE_ID` і `WORKSHOP_SLACK_CHANNEL_ID`. Наявність app-токена вмикає локальний режим. Він використовує `xapp` для WebSocket і `xoxb` для публікацій. Signing Secret і Router URL для цього режиму не потрібні.
3. Запусти один локальний бекенд із кореня репозиторію. Якщо інший бекенд уже займає порт 8000, спочатку зупини його.

   ```sh
   cd backend
   DATA_DIR=../var/workshop-local RUN_WORKER=true .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```

   У журналі очікуємо `Slack Socket Mode connected`. Якщо Slack повертає `invalid_auth` або `missing_scope`, перевір app-токен і `connections:write`. Якщо сокет підключений, а код не спрацьовує, перевір `message.im` і що пишеш боту в DM із потрібного workspace.
4. Виконай три локальні запити з розділу «Що перевірити наживо». Між першим і другим запитом надішли боту `pair <код>`. Після `connected` створи задачу з отриманим `reporter_id`. У тестовому каналі очікуємо одне повідомлення зі згадкою та ключем задачі.

### Вхідні події у локальному Socket Mode

У **Event Subscriptions → Subscribe to bot events** додай `message.channels` для публічного каналу або `message.groups` для приватного. Потрібні відповідно `channels:history` або `groups:history`. Після зміни scopes перевстанови застосунок, якщо Slack просить цього. У **Interactivity & Shortcuts** увімкни **Interactivity**. У Socket Mode Slack доставляє кнопки через те саме з’єднання. [Публічні канали](https://docs.slack.dev/reference/events/message.channels/) · [Приватні канали](https://docs.slack.dev/reference/events/message.groups/) · [Interactivity через Socket Mode](https://docs.slack.dev/apis/events-api/using-socket-mode/)

Для перевірки напиши одну репліку в треді навчальної задачі й натисни кнопку в опублікованій чернетці. Бекенд зберігає події в локальному журналі прогону. Після схвалення актуальної чернетки перевір у навчальній Jira, що до початкового опису додався один погоджений блок, а в тому самому треді з’явилося підтвердження.

## Socket Mode для кількох ноутбуків у приватній мережі

Один спільний процес приймає події Slack через вихідний WebSocket. Локальні бекенди учасників забирають свої події через приватну адресу цього процесу. Slack Request URL, публічний порт і тунель для цього режиму не потрібні. [Slack Socket Mode](https://docs.slack.dev/apis/events-api/using-socket-mode/)

1. На машині маршрутизатора задай `WORKSHOP_SLACK_APP_TOKEN`, `WORKSHOP_SLACK_BOT_TOKEN`, `WORKSHOP_SLACK_WORKSPACE_ID` і `WORKSHOP_SLACK_CHANNEL_ID`. Запусти з каталогу `backend`:

   ```sh
   DATA_DIR=../var/workshop-router .venv/bin/uvicorn app.slack_router:app      --host 192.168.1.20 --port 8010
   ```

   Заміни `192.168.1.20` на приватну IP-адресу машини маршрутизатора. Для доступу з ноутбуків використовуй приватний HTTPS або захищену VPN-мережу. Доступ до порту залиш у межах цієї мережі. На час цього прогону використовуй один приймач Socket Mode для застосунку. Slack може доставляти події будь-якому з одночасно підключених сокетів. [Кілька з’єднань Socket Mode](https://docs.slack.dev/apis/events-api/using-socket-mode/)

2. На кожному ноутбуці задай `WORKSHOP_SLACK_ROUTER_URL` рівним приватній адресі маршрутизатора й залиш `WORKSHOP_SLACK_APP_TOKEN` порожнім. Запусти локальний бекенд із власною базою та `RUN_WORKER=true`. Кожен учасник прив’язує свій Slack-акаунт через `POST /api/jira/workshop/pairing` і перевіряє `GET /api/jira/workshop/pairing`.
3. Учасники створюють окремі навчальні задачі й працюють у своїх тредах. Для перевірки перепідключення вимкни один локальний бекенд, надішли репліку або натисни кнопку в його треді й запусти бекенд з тією самою базою. Подія має з’явитися один раз у його локальному журналі. Інший екземпляр її не отримає.

Маршрутизатор зберігає подію до підтвердження. Локальний бекенд підтверджує її після коміту до своєї бази. Якщо зв’язок обірветься між комітом і підтвердженням, повторну доставку поглине унікальний `event_id`.

## 1. Що підготувати у Slack

1. У [Slack App Management](https://api.slack.com/apps) створи Slack App для тестового workspace або отримай доступ до налаштувань наявного воркшопного застосунку. Якщо встановлення контролює адміністратор, попроси схвалити встановлення та наведені нижче права.
2. У **OAuth & Permissions → Bot Token Scopes** додай `im:history` для приймання повідомлень у DM і `chat:write` для публікації. У **App Home** увімкни **Messages Tab** і дозволь користувачам писати застосунку, якщо Slack показує такий перемикач. Встанови застосунок у workspace. Після зміни прав перевстанови його, якщо Slack цього вимагає. [Приватні повідомлення застосунку](https://docs.slack.dev/surfaces/app-home/#using-the-messages-tab) · [Публікація повідомлень](https://docs.slack.dev/reference/methods/chat.postMessage/)
3. Створи або вибери тестовий канал, наприклад `#ai-workshop-test`. Додай туди бота й акаунт, з якого проходитимеш перевірку. Скопіюй **Workspace ID** і **Channel ID**. Для сповіщення про згадку репортер має бути учасником каналу. [Згадки в Slack](https://docs.slack.dev/messaging/formatting-message-text/#mentioning-users)
4. Знайди **Signing Secret** у **Basic Information → App Credentials** і **Bot User OAuth Token** в **OAuth & Permissions**. Збережи обидва в секретах процесу маршрутизатора. Для координації можна передати назву workspace, канал, ID та HTTPS-адресу. Токен і Signing Secret залишаються в конфігурації. [Перевірка підписів Slack](https://docs.slack.dev/authentication/verifying-requests-from-slack/)

## 2. Запуск двох процесів

Запускаємо **один спільний маршрутизатор** і **локальний бекенд учасника**. Маршрутизатор приймає події від Slack і відправляє повідомлення ботом. Локальний бекенд звертається до маршрутизатора вихідними HTTP-запитами. Для першого тесту обидва можуть працювати на одному ноутбуці з різними портами й каталогами даних. Публічний HTTPS веде лише до маршрутизатора.

| Де задати | Змінна | Значення |
| --- | --- | --- |
| Маршрутизатор | `WORKSHOP_SLACK_WORKSPACE_ID` | ID тестового workspace |
| Маршрутизатор | `WORKSHOP_SLACK_CHANNEL_ID` | ID тестового каналу |
| Маршрутизатор | `WORKSHOP_SLACK_SIGNING_SECRET` | Signing Secret застосунку |
| Маршрутизатор | `WORKSHOP_SLACK_BOT_TOKEN` | Bot User OAuth Token |
| Локальний бекенд | `WORKSHOP_SLACK_ROUTER_URL` | Базова HTTPS-адреса маршрутизатора без `/slack/events` |
| Локальний бекенд | `RUN_WORKER` | `true` для тесту з вбудованим worker |

Приклад команд із кореня репозиторію, коли локальне середовище `backend/.venv` готове. Запусти в окремих терміналах із відповідними змінними.

```sh
# Спільний маршрутизатор. HTTPS-проксі або тунель веде на порт 8010.
cd backend
DATA_DIR=../var/workshop-router .venv/bin/uvicorn app.slack_router:app --host 127.0.0.1 --port 8010
```

```sh
# Локальний бекенд учасника.
cd backend
DATA_DIR=../var/workshop-local RUN_WORKER=true .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Якщо задано `DATABASE_URL`, перевір, що процеси використовують окремі бази. Локальному бекенду потрібна лише адреса маршрутизатора. Наявний `SLACK_WEBHOOK_URL` належить до CI-сповіщень.

Коли маршрутизатор доступний через HTTPS, у Slack відкрий **Event Subscriptions → Enable Events**, введи `https://<адреса-маршрутизатора>/slack/events` і дочекайся **Verified**. У **Subscribe to bot events** додай `message.im` і збережи зміни. Поточний код приймає підписані HTTP-події Slack. [Налаштування Request URL](https://docs.slack.dev/apis/events-api/using-http-request-urls/) · [Подія message.im](https://docs.slack.dev/reference/events/message.im/)

## 3. Що перевірити наживо

1. У локальному бекенді виклич `POST /api/jira/workshop/pairing`. Код з відповіді діє п’ять хвилин.

   ```sh
   curl -fsS -X POST http://127.0.0.1:8000/api/jira/workshop/pairing
   ```

2. У приватному діалозі з ботом надішли `pair <код>`. Перевір стан локальним запитом. У відповіді очікуємо `connected`, твій `slack_user_id`, `profile_id` і навчальний `reporter_id`.

   ```sh
   curl -fsS http://127.0.0.1:8000/api/jira/workshop/pairing
   ```

3. Створи одну навчальну задачу. Підстав `reporter_id` з попередньої відповіді.

   ```sh
   curl -fsS -X POST http://127.0.0.1:8000/api/jira/training/issues \
     -H 'Content-Type: application/json' \
     -d '{"reporter_id":"<reporter_id>"}'
   ```

4. У тестовому каналі має з’явитися одне кореневе повідомлення зі згадкою, ключем задачі й позначкою **«Навчальна Jira»**. Дочекайся кількох циклів worker і перевір, що другого повідомлення з цим ключем немає. Для перевірки перезапуску використай ту саму локальну базу й ту саму базу маршрутизатора.

Якщо URL не переходить у **Verified**, перевір публічний HTTPS, точний шлях і Signing Secret. Якщо статус лишається `pending`, перевір `message.im`, права застосунку, workspace і строк дії коду. Якщо підключення є, але повідомлення немає, перевір worker, членство бота в каналі, ID каналу й токен. Для пошуку причин локально дивись журнал worker і стан операції `open_thread`.

Цим тестом приймаємо живу прив’язку **W09** і відкриття треду з **W10**. Репліки, кнопки й обробка відповідей потребують завершення W10–W11. Екран підключення входить у W12. Request URL для інтерактивних кнопок налаштовуємо, коли з’явиться їхній обробник.

## 4. Що попросити для справжньої Jira

- Підтвердити, чи це **Jira Cloud**, і отримати базову адресу та ключ окремого тестового проєкту.
- Отримати тестовий акаунт, який може бачити задачу, створити баг від свого імені та змінити поле **Description**. Для читання й редагування перевір права **Browse Projects** та **Edit Issues**, а для створення — **Create Issues**. [Права Jira Cloud для операцій із задачами](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/)
- Перевірити, що в тестовому проєкті є потрібний початковий статус, а в тестовій задачі акаунт записаний як **Reporter**.
- Уточнити в адміністратора, який спосіб API-підключення дозволено. Вибір способу входу й перевірка запису належать до W18–W19.

Справжня Jira не потрібна, щоб перевірити Slack зараз. Якщо доступ до Jira буде лише в частини групи, інші учасники проходять той самий сценарій у навчальному режимі.

[Беклог і поточні блокери](jira-slack-workshop-backlog.md) · [Профіль і локальний запуск воркшопу](../../demo/jira-workshop/README.md)
