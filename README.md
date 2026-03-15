# Telegram-репетитор по математике для 5 класса

Бот для Telegram, который:
- не даёт готовые ответы;
- мягко подводит ребёнка к самостоятельному решению;
- принимает текст, PDF, DOCX, JPG/PNG;
- помогает как репетитор 5 класса.

## 1. Что нужно
- аккаунт Telegram
- бот, созданный через @BotFather
- аккаунт GitHub
- аккаунт Railway

## 2. Создать бота в Telegram
1. Откройте @BotFather
2. Отправьте `/newbot`
3. Получите токен
4. Сохраните токен

## 3. Загрузка в GitHub
1. Создайте новый репозиторий на GitHub
2. Загрузите в него все файлы из этой папки
3. Не загружайте `.env`, если будете хранить токен в Railway Variables

## 4. Размещение в Railway
1. Войдите в Railway через GitHub
2. Нажмите **New Project**
3. Выберите **Deploy from GitHub Repo**
4. Выберите ваш репозиторий
5. Откройте сервис -> **Variables**
6. Добавьте переменную:
   - `BOT_TOKEN` = ваш токен от BotFather
7. Откройте **Settings**
8. В поле **Start Command** укажите:

```bash
python bot.py
```

9. Дождитесь успешного деплоя
10. Откройте бота в Telegram и нажмите `/start`

## 5. JPG и OCR
Чтобы бот читал JPG/PNG на Railway, добавьте во вкладке Variables:
- `RAILPACK_DEPLOY_APT_PACKAGES` = `tesseract-ocr tesseract-ocr-rus`

Потом сделайте Redeploy.

## 6. Локальный запуск (необязательно)
```bash
pip install -r requirements.txt
python bot.py
```

Перед локальным запуском задайте переменную окружения `BOT_TOKEN`.
