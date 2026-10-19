import os
import json
import vk_api
from vk_api.longpoll import VkLongPoll, VkEventType
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
from vk_api.utils import get_random_id

# ==========================================
# НАСТРОЙКИ
# ==========================================
TOKEN = os.getenv('VK_TOKEN') or "ТВОЙ_ТОКЕН_ЗДЕСЬ"

# Впишите сюда ID и ссылки (в кавычках). Бот сам разберется, где цифры, а где буквы.
RAW_ADMIN_IDS = [577603865, 410091203, "ekaterina_zaychenko_fh"] 

TASKS_FILE = "tasks.json"
user_states = {}

# Эта функция превращает короткую ссылку (буквы) в цифровой ID
def resolve_admins(vk, raw_list):
    resolved = []
    for admin in raw_list:
        if isinstance(admin, int):
            resolved.append(admin)
        elif isinstance(admin, str):
            try:
                # Просим ВК найти пользователя по ссылке
                res = vk.users.get(user_ids=admin)
                if res:
                    resolved.append(res[0]['id'])
            except Exception as e:
                print(f"Ошибка: не удалось найти пользователя {admin}: {e}")
    return resolved

# ==========================================
# ФУНКЦИИ ДЛЯ РАБОТЫ С ЗАДАНИЯМИ
# ==========================================
def load_tasks():
    if os.path.exists(TASKS_FILE):
        with open(TASKS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_tasks(tasks):
    with open(TASKS_FILE, "w", encoding="utf-8") as f:
        json.dump(tasks, f, ensure_ascii=False, indent=4)

# ==========================================
# КЛАВИАТУРА И ОТПРАВКА
# ==========================================
def get_main_keyboard(user_id, admin_ids):
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button('Задания', color=VkKeyboardColor.POSITIVE)
    keyboard.add_button('Сдать работу', color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button('Помощь', color=VkKeyboardColor.SECONDARY)
    
    if user_id in admin_ids:
        keyboard.add_button('Добавить задание', color=VkKeyboardColor.NEGATIVE)
    return keyboard.get_keyboard()

def send_msg(vk, user_id, message, keyboard=None):
    try:
        vk.messages.send(user_id=user_id, message=message, random_id=get_random_id(), keyboard=keyboard)
    except Exception as e:
        print(f"Ошибка отправки пользователю {user_id}: {e}")

# ==========================================
# ОСНОВНАЯ ЛОГИКА
# ==========================================
def main():
    vk_session = vk_api.VkApi(token=TOKEN)
    vk = vk_session.get_api()
    longpoll = VkLongPoll(vk_session)
    
    # Превращаем ссылки в цифры перед запуском
    ADMIN_IDS = resolve_admins(vk, RAW_ADMIN_IDS)
    print(f"Бот запущен! ID преподавателей: {ADMIN_IDS}")
    print("Бот слушает сообщения...")

    for event in longpoll.listen():
        if event.type == VkEventType.MESSAGE_NEW and event.to_me:
            request = event.text.lower().strip()
            user_id = event.user_id
            
            # 1. СТАРТ
            if request in ['/start', 'начать', 'привет']:
                user_states[user_id] = None
                send_msg(vk, user_id, "Привет! Я бот для сдачи работ по СМИ. Выбери действие 👇", keyboard=get_main_keyboard(user_id, ADMIN_IDS))

            # 2. ЗАДАНИЯ
            elif request == 'задания':
                user_states[user_id] = None
                tasks = load_tasks()
                if not tasks:
                    text = "📭 На данный момент активных заданий нет."
                else:
                    text = "📋 **Актуальные задания по СМИ:**\n\n"
                    for i, task in enumerate(tasks, 1):
                        text += f"{i}️⃣ **{task['title']}**\nОписание: {task['desc']}\n⏳ Дедлайн: {task['deadline']}\n\n"
                send_msg(vk, user_id, text, keyboard=get_main_keyboard(user_id, ADMIN_IDS))

            # 3. ПОМОЩЬ
            elif request == 'помощь':
                user_states[user_id] = None
                help_text = "📞 **Контакты:**\nИванов И.И.\nКабинет: 302\n\n📌 **Правила:**\n1. Сдавать работы только через бота.\n2. Указывайте номер задания."
                send_msg(vk, user_id, help_text, keyboard=get_main_keyboard(user_id, ADMIN_IDS))

            # 4. СДАТЬ РАБОТУ
            elif request == 'сдать работу':
                user_states[user_id] = 'waiting_for_work'
                send_msg(vk, user_id, "Отправьте текст работы или прикрепите файл.", keyboard=get_main_keyboard(user_id, ADMIN_IDS))

            # 5. ДОБАВИТЬ ЗАДАНИЕ (ТОЛЬКО ПРЕПОДАВАТЕЛИ)
            elif request == 'добавить задание' and user_id in ADMIN_IDS:
                user_states[user_id] = 'waiting_for_new_task'
                send_msg(vk, user_id, "Введите задание в формате:\n**Название** | **Описание** | **Дедлайн**\n\nПример:\nНаписать заметку | Про концерт | Пятница 18:00", keyboard=get_main_keyboard(user_id, ADMIN_IDS))

            # 6. СОХРАНЕНИЕ ЗАДАНИЯ
            elif user_states.get(user_id) == 'waiting_for_new_task' and user_id in ADMIN_IDS:
                try:
                    parts = [p.strip() for p in event.text.split('|')]
                    if len(parts) == 3:
                        tasks = load_tasks()
                        tasks.append({"title": parts[0], "desc": parts[1], "deadline": parts[2]})
                        save_tasks(tasks)
                        user_states[user_id] = None
                        send_msg(vk, user_id, "✅ Задание добавлено!", keyboard=get_main_keyboard(user_id, ADMIN_IDS))
                    else:
                        send_msg(vk, user_id, "❌ Ошибка формата. Используйте два разделителя |", keyboard=get_main_keyboard(user_id, ADMIN_IDS))
                except Exception as e:
                    send_msg(vk, user_id, f"❌ Ошибка: {e}", keyboard=get_main_keyboard(user_id, ADMIN_IDS))

            # 7. ПРИЕМ РАБОТЫ И ПЕРЕСЫЛКА
            elif user_states.get(user_id) == 'waiting_for_work':
                attachments = event.attachments
                if attachments or event.text:
                    print(f"Студент ID {user_id} сдал работу.")
                    send_msg(vk, user_id, "✅ Работа получена! Передал преподавателю.", keyboard=get_main_keyboard(user_id, ADMIN_IDS))
                    
                    for admin_id in ADMIN_IDS:
                        try:
                            vk.messages.send(
                                user_id=admin_id,
                                message=f"📥 **Новая работа!**\nОт студента (ID: {user_id}).",
                                forward_messages=event.message_id,
                                random_id=get_random_id()
                            )
                        except Exception as e:
                            print(f"Ошибка пересылки {admin_id}: {e}")
                    user_states[user_id] = None

            # 8. НЕИЗВЕСТНАЯ КОМАНДА
            else:
                if user_states.get(user_id) == 'waiting_for_work':
                     send_msg(vk, user_id, "Пожалуйста, отправьте текст или файл.", keyboard=get_main_keyboard(user_id, ADMIN_IDS))
                else:
                     send_msg(vk, user_id, "Я не понимаю команду. Используйте кнопки 👇", keyboard=get_main_keyboard(user_id, ADMIN_IDS))

if __name__ == '__main__':
    main()
