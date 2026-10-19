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
RAW_ADMIN_IDS = [577603865, 410091203, "ekaterina_zaychenko_fh"] 

TASKS_FILE = "tasks.json"
STUDENTS_FILE = "students.json"
SUBMISSIONS_FILE = "submissions.json" # Файл для сданных работ
user_states = {}

# Превращаем ссылки в ID
def resolve_admins(vk, raw_list):
    resolved = []
    for admin in raw_list:
        if isinstance(admin, int):
            resolved.append(admin)
        elif isinstance(admin, str):
            try:
                res = vk.users.get(user_ids=admin)
                if res:
                    resolved.append(res[0]['id'])
            except Exception:
                pass
    return resolved

# ==========================================
# ФУНКЦИИ РАБОТЫ С ФАЙЛАМИ
# ==========================================
def load_data(filename, default_type=dict):
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    return default_type() if callable(default_type) else default_type

def save_data(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# ==========================================
# КЛАВИАТУРЫ
# ==========================================
def get_main_keyboard(user_id, admin_ids):
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button('Задания', color=VkKeyboardColor.POSITIVE)
    keyboard.add_button('Сдать работу', color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button('Помощь', color=VkKeyboardColor.SECONDARY)
    
    if user_id in admin_ids:
        keyboard.add_button('Добавить задание', color=VkKeyboardColor.NEGATIVE)
        keyboard.add_button('Проверить работы', color=VkKeyboardColor.SECONDARY) # Новая кнопка для препода
    return keyboard.get_keyboard()

def get_review_keyboard():
    """Клавиатура для оценки работы (только для преподавателя)"""
    keyboard = VkKeyboard(one_time=True)
    keyboard.add_button('✅ Зачесть', color=VkKeyboardColor.POSITIVE)
    keyboard.add_button('❌ Отклонить', color=VkKeyboardColor.NEGATIVE)
    keyboard.add_line()
    keyboard.add_button('✍️ Комментарий', color=VkKeyboardColor.PRIMARY)
    keyboard.add_button('⏭ Пропустить', color=VkKeyboardColor.SECONDARY)
    return keyboard.get_keyboard()

# ==========================================
# ОТПРАВКА И ЛОГИКА ПРОВЕРКИ
# ==========================================
def send_msg(vk, user_id, message, keyboard=None, forward_messages=None):
    try:
        vk.messages.send(user_id=user_id, message=message, random_id=get_random_id(), keyboard=keyboard, forward_messages=forward_messages)
    except Exception as e:
        print(f"Ошибка отправки пользователю {user_id}: {e}")

def show_next_submission(vk, admin_id, admin_ids, current_task_id=None):
    """Ищет следующую непроверенную работу и отправляет ее преподу"""
    submissions = load_data(SUBMISSIONS_FILE, list)
    
    # Ищем работу со статусом pending (в ожидании)
    for i, sub in enumerate(submissions):
        if sub['status'] == 'pending' and sub['id'] != current_task_id:
            # Нашли работу!
            user_states[admin_id] = {'state': 'reviewing', 'task_id': sub['id']}
            
            msg = (
                f"📥 **Работа №{sub['id']}**\n\n"
                f"👤 **Студент:** {sub['student_info']}\n"
                f"📝 **Задание:** {sub['task_title']}\n\n"
                f"Оцените работу с помощью кнопок ниже 👇"
            )
            # Отправляем текст и пересылаем оригинальное сообщение с файлами
            send_msg(vk, admin_id, msg, keyboard=get_review_keyboard(), forward_messages=sub['message_id'])
            return

    # Если ничего не нашли
    send_msg(vk, admin_id, "🎉 Все работы проверены! Новых заданий на проверку нет.", keyboard=get_main_keyboard(admin_id, admin_ids))
    user_states[admin_id] = None

# ==========================================
# ОСНОВНАЯ ЛОГИКА
# ==========================================
def main():
    vk_session = vk_api.VkApi(token=TOKEN)
    vk = vk_session.get_api()
    longpoll = VkLongPoll(vk_session)
    
    ADMIN_IDS = resolve_admins(vk, RAW_ADMIN_IDS)
    print(f"Бот запущен! Преподаватели: {ADMIN_IDS}")

    for event in longpoll.listen():
        if event.type == VkEventType.MESSAGE_NEW and event.to_me:
            request = event.text.lower().strip()
            user_id = event.user_id
            
            # --- СТУДЕНЧЕСКИЕ КОМАНДЫ ---
            if request in ['/start', 'начать', 'привет']:
                user_states[user_id] = None
                send_msg(vk, user_id, "Привет! Я бот для сдачи работ по СМИ. Выбери действие 👇", keyboard=get_main_keyboard(user_id, ADMIN_IDS))

            elif request == 'задания':
                user_states[user_id] = None
                tasks = load_data(TASKS_FILE, list)
                if not tasks:
                    text = "📭 На данный момент активных заданий нет."
                else:
                    text = "📋 **Актуальные задания по СМИ:**\n\n"
                    for i, task in enumerate(tasks, 1):
                        text += f"{i}️⃣ **{task['title']}**\nОписание: {task['desc']}\n⏳ Дедлайн: {task['deadline']}\n\n"
                send_msg(vk, user_id, text, keyboard=get_main_keyboard(user_id, ADMIN_IDS))

            elif request == 'помощь':
                user_states[user_id] = None
                help_text = "📞 **Контакты:**\nИванов И.И.\nКабинет: 302\n\n📌 **Правила:**\n1. Сдавать работы только через бота.\n2. Указывайте номер задания."
                send_msg(vk, user_id, help_text, keyboard=get_main_keyboard(user_id, ADMIN_IDS))

            elif request == 'сдать работу':
                students = load_data(STUDENTS_FILE, dict)
                if str(user_id) not in students:
                    user_states[user_id] = 'waiting_for_name_group'
                    send_msg(vk, user_id, "Перед сдачей работы нужно представиться.\n\nНапишите ваше **ФИО и Группу** одним сообщением.\nПример:\n*Иванов Иван Иванович, группа ИС-21*", keyboard=get_main_keyboard(user_id, ADMIN_IDS))
                else:
                    user_states[user_id] = 'waiting_for_work'
                    send_msg(vk, user_id, "Отправьте текст работы или прикрепите файл (фото/видео/документ).\n\n*Не забудьте указать, какое именно задание вы выполняете.*", keyboard=get_main_keyboard(user_id, ADMIN_IDS))

            elif user_states.get(user_id) == 'waiting_for_name_group':
                students = load_data(STUDENTS_FILE, dict)
                students[str(user_id)] = event.text
                save_data(STUDENTS_FILE, students)
                
                user_states[user_id] = 'waiting_for_work'
                send_msg(vk, user_id, "✅ Данные сохранены!\nТеперь отправьте текст работы или прикрепите файл (и укажите номер/название задания).", keyboard=get_main_keyboard(user_id, ADMIN_IDS))

            elif user_states.get(user_id) == 'waiting_for_work':
                attachments = event.attachments
                if attachments or event.text:
                    students = load_data(STUDENTS_FILE, dict)
                    student_info = students.get(str(user_id), "Данные не указаны")
                    
                    # Сохраняем работу в файл submissions.json
                    submissions = load_data(SUBMISSIONS_FILE, list)
                    new_id = len(submissions) + 1
                    
                    # Берем первые 30 символов сообщения как название задания для удобства
                    task_title = event.text[:30] + "..." if len(event.text) > 30 else event.text
                    if not task_title: task_title = "Файл/Медиа"
                    
                    submissions.append({
                        "id": new_id,
                        "student_id": user_id,
                        "student_info": student_info,
                        "task_title": task_title,
                        "message_id": event.message_id,
                        "status": "pending"
                    })
                    save_data(SUBMISSIONS_FILE, submissions)
                    
                    send_msg(vk, user_id, "✅ Работа получена и отправлена преподавателю на проверку!", keyboard=get_main_keyboard(user_id, ADMIN_IDS))
                    
                    # Уведомляем преподователей, что пришла работа
                    for admin_id in ADMIN_IDS:
                        send_msg(vk, admin_id, f"🔔 Поступила новая работа от студента {student_info}!\nНажмите 'Проверить работы' в меню.", keyboard=get_main_keyboard(admin_id, ADMIN_IDS))
                        
                    user_states[user_id] = None

            # --- ПРЕПОДАВАТЕЛЬСКИЕ КОМАНДЫ ---
            elif request == 'добавить задание' and user_id in ADMIN_IDS:
                user_states[user_id] = 'waiting_for_new_task'
                send_msg(vk, user_id, "Введите задание в формате:\n**Название** | **Описание** | **Дедлайн**\n\nПример:\nНаписать заметку | Про концерт | Пятница 18:00", keyboard=get_main_keyboard(user_id, ADMIN_IDS))

            elif user_states.get(user_id) == 'waiting_for_new_task' and user_id in ADMIN_IDS:
                try:
                    parts = [p.strip() for p in event.text.split('|')]
                    if len(parts) == 3:
                        tasks = load_data(TASKS_FILE, list)
                        tasks.append({"title": parts[0], "desc": parts[1], "deadline": parts[2]})
                        save_data(TASKS_FILE, tasks)
                        user_states[user_id] = None
                        send_msg(vk, user_id, "✅ Задание добавлено!", keyboard=get_main_keyboard(user_id, ADMIN_IDS))
                    else:
                        send_msg(vk, user_id, "❌ Ошибка формата. Используйте два разделителя |", keyboard=get_main_keyboard(user_id, ADMIN_IDS))
                except Exception as e:
                    send_msg(vk, user_id, f"❌ Ошибка: {e}", keyboard=get_main_keyboard(user_id, ADMIN_IDS))

            elif request == 'проверить работы' and user_id in ADMIN_IDS:
                show_next_submission(vk, user_id, ADMIN_IDS)

            # Обработка кнопок оценки работы
            elif request in ['✅ зачесть', '❌ отклонить', '✍️ комментарий', '⏭ пропустить'] and user_id in ADMIN_IDS:
                state = user_states.get(user_id, {})
                if state.get('state') not in ['reviewing', 'waiting_for_feedback']:
                    continue
                
                task_id = state['task_id']
                submissions = load_data(SUBMISSIONS_FILE, list)
                current_task = next((t for t in submissions if t['id'] == task_id), None)
                
                if not current_task:
                    send_msg(vk, user_id, "Работа не найдена. Возможно, она уже проверена.", keyboard=get_main_keyboard(user_id, ADMIN_IDS))
                    user_states[user_id] = None
                    continue

                student_id = current_task['student_id']
                task_title = current_task['task_title']

                if request == '⏭ пропустить':
                    show_next_submission(vk, user_id, ADMIN_IDS, current_task_id=task_id)
                    
                elif request == '✅ зачесть':
                    current_task['status'] = 'accepted'
                    save_data(SUBMISSIONS_FILE, submissions)
                    send_msg(vk, student_id, f"✅ **Преподаватель проверил вашу работу!**\nЗадание: {task_title}\nСтатус: **Зачтено**.")
                    send_msg(vk, user_id, f"Работа №{task_id} зачтена!")
                    show_next_submission(vk, user_id, ADMIN_IDS)
                    
                elif request == '❌ отклонить':
                    current_task['status'] = 'rejected'
                    save_data(SUBMISSIONS_FILE, submissions)
                    send_msg(vk, student_id, f"❌ **Преподаватель проверил вашу работу!**\nЗадание: {task_title}\nСтатус: **Отклонено (нужна доработка)**.")
                    send_msg(vk, user_id, f"Работа №{task_id} отклонена.")
                    show_next_submission(vk, user_id, ADMIN_IDS)
                    
                elif request == '✍️ комментарий':
                    user_states[user_id] = {'state': 'waiting_for_feedback', 'task_id': task_id}
                    send_msg(vk, user_id, "Напишите текст комментария/оценки для студента одним сообщением:")

            # Обработка текста комментария от преподавателя
            elif user_states.get(user_id, {}).get('state') == 'waiting_for_feedback' and user_id in ADMIN_IDS:
                task_id = user_states[user_id]['task_id']
                submissions = load_data(SUBMISSIONS_FILE, list)
                current_task = next((t for t in submissions if t['id'] == task_id), None)
                
                if current_task:
                    student_id = current_task['student_id']
                    task_title = current_task['task_title']
                    
                    # Меняем статус и сохраняем
                    current_task['status'] = 'commented'
                    save_data(SUBMISSIONS_FILE, submissions)
                    
                    # Отправляем студенту
                    send_msg(vk, student_id, f"📩 **Ответ от преподавателя:**\n\n{event.text}")
                    send_msg(vk, user_id, f"✅ Комментарий отправлен студенту.")
                
                show_next_submission(vk, user_id, ADMIN_IDS)

            # --- ОБРАБОТКА НЕИЗВЕСТНЫХ КОМАНД ---
            else:
                if user_states.get(user_id) == 'waiting_for_work':
                     send_msg(vk, user_id, "Пожалуйста, отправьте текст работы или файл.", keyboard=get_main_keyboard(user_id, ADMIN_IDS))
                elif user_states.get(user_id) == 'waiting_for_name_group':
                     send_msg(vk, user_id, "Пожалуйста, напишите ваше ФИО и группу (например: Иванов Иван, ИС-21).", keyboard=get_main_keyboard(user_id, ADMIN_IDS))
                else:
                     send_msg(vk, user_id, "Я не понимаю команду. Используйте кнопки 👇", keyboard=get_main_keyboard(user_id, ADMIN_IDS))

if __name__ == '__main__':
    main()
