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

# ⚠️ СПИСОК ПРЕПОДАВАТЕЛЕЙ
RAW_ADMIN_IDS = [577603865, 410091203, "ekaterina_zaychenko_fh", "segatakai"] 

TASKS_FILE = "tasks.json"
STUDENTS_FILE = "students.json"
SUBMISSIONS_FILE = "submissions.json"
user_states = {}

def resolve_admins(vk, raw_list):
    resolved = []
    for admin in raw_list:
        if isinstance(admin, int):
            resolved.append(admin)
        elif isinstance(admin, str):
            try:
                clean_admin = admin.replace('@', '')
                res = vk.users.get(user_ids=clean_admin)
                if res:
                    resolved.append(res[0]['id'])
            except Exception as e:
                print(f"Не удалось найти преподавателя {admin}: {e}")
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

def get_student(user_id):
    students = load_data(STUDENTS_FILE, dict)
    sid = str(user_id)
    if sid not in students:
        return None, students
    
    if isinstance(students[sid], str):
        students[sid] = {"name": students[sid], "points": 0}
        save_data(STUDENTS_FILE, students)
        
    return students[sid], students

# ==========================================
# КЛАВИАТУРЫ
# ==========================================
def get_main_keyboard(user_id, admin_ids):
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button('Задания', color=VkKeyboardColor.POSITIVE)
    keyboard.add_button('Сдать работу', color=VkKeyboardColor.PRIMARY)
    keyboard.add_button('Топ лучших', color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button('Помощь', color=VkKeyboardColor.SECONDARY)
    
    if user_id in admin_ids:
        keyboard.add_button('Добавить задание', color=VkKeyboardColor.NEGATIVE)
        keyboard.add_button('Удалить задание', color=VkKeyboardColor.NEGATIVE)
        keyboard.add_line()
        keyboard.add_button('Проверить работы', color=VkKeyboardColor.SECONDARY)
    return keyboard.get_keyboard()

def get_review_keyboard():
    keyboard = VkKeyboard(one_time=True)
    keyboard.add_button('✅ Оценить', color=VkKeyboardColor.POSITIVE)
    keyboard.add_button('❌ Отклонить', color=VkKeyboardColor.NEGATIVE)
    keyboard.add_line()
    keyboard.add_button('✍️ Только комментарий', color=VkKeyboardColor.PRIMARY)
    keyboard.add_button('⏭ Пропустить', color=VkKeyboardColor.SECONDARY)
    return keyboard.get_keyboard()

# ==========================================
# ОТПРАВКА И ЛОГИКА
# ==========================================
def send_msg(vk, user_id, message, keyboard=None, forward_messages=None):
    try:
        vk.messages.send(user_id=user_id, message=message, random_id=get_random_id(), keyboard=keyboard, forward_messages=forward_messages)
    except Exception as e:
        print(f"Ошибка отправки пользователю {user_id}: {e}")

def show_leaderboard(vk, user_id, admin_ids):
    students = load_data(STUDENTS_FILE, dict)
    if not students:
        send_msg(vk, user_id, "Пока нет ни одного студента в базе.", keyboard=get_main_keyboard(user_id, admin_ids))
        return

    leaderboard = []
    for uid, data in students.items():
        if isinstance(data, str):
            leaderboard.append({"name": data, "points": 0})
        else:
            leaderboard.append({"name": data.get("name", "Неизвестный"), "points": data.get("points", 0)})
    
    leaderboard.sort(key=lambda x: x["points"], reverse=True)
    text = "🏆 ТОП ЛУЧШИХ СТУДЕНТОВ:\n\n"
    medals = ["🥇", "🥈", "🥉"]
    
    for i, student in enumerate(leaderboard[:10]):
        medal = medals[i] if i < 3 else "🔹"
        text += f"{medal} {student['name']} — {student['points']} баллов\n"
        
    send_msg(vk, user_id, text, keyboard=get_main_keyboard(user_id, admin_ids))

def show_next_submission(vk, admin_id, admin_ids, current_task_id=None):
    submissions = load_data(SUBMISSIONS_FILE, list)
    
    for sub in submissions:
        if sub['status'] == 'pending' and sub['id'] != current_task_id:
            user_states[admin_id] = {'state': 'reviewing', 'task_id': sub['id']}
            
            msg = (
                f"📥 Работа №{sub['id']}\n\n"
                f"👤 Студент: {sub['student_info']}\n"
                f"📝 Задание: {sub['task_title']}\n\n"
                f"Оцените работу с помощью кнопок ниже 👇"
            )
            send_msg(vk, admin_id, msg, keyboard=get_review_keyboard(), forward_messages=sub['message_id'])
            return

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
                    text = "📋 Актуальные задания по СМИ:\n\n"
                    for i, task in enumerate(tasks, 1):
                        text += f"{i}️⃣ {task['title']}\nОписание: {task['desc']}\n⏳ Дедлайн: {task['deadline']}\n\n"
                send_msg(vk, user_id, text, keyboard=get_main_keyboard(user_id, ADMIN_IDS))

            elif request == 'топ лучших':
                user_states[user_id] = None
                show_leaderboard(vk, user_id, ADMIN_IDS)

            elif request == 'помощь':
                user_states[user_id] = None
                help_text = "📞 Контакты:\nСмородина Е.Л.\n ВК: @ekaterina_zaychenko_fh\n\n📌 Правила:\n1. Сдавать работы только через бота.\n2. За каждую работу преподаватель ставит от 1 до 10 баллов."
                send_msg(vk, user_id, help_text, keyboard=get_main_keyboard(user_id, ADMIN_IDS))

            elif request == 'сдать работу':
                student, _ = get_student(user_id)
                if not student:
                    user_states[user_id] = 'waiting_for_name_group'
                    send_msg(vk, user_id, "Перед сдачей работы нужно представиться.\n\nНапишите ваше ФИО и Группу одним сообщением.\nПример:\nИванов Иван Иванович, группа ИС-21", keyboard=get_main_keyboard(user_id, ADMIN_IDS))
                else:
                    user_states[user_id] = 'waiting_for_work'
                    send_msg(vk, user_id, f"Вы: {student['name']} (Баллов: {student['points']})\n\nОтправьте текст работы или прикрепите файл.", keyboard=get_main_keyboard(user_id, ADMIN_IDS))

            elif user_states.get(user_id) == 'waiting_for_name_group':
                students = load_data(STUDENTS_FILE, dict)
                students[str(user_id)] = {"name": event.text, "points": 0}
                save_data(STUDENTS_FILE, students)
                
                user_states[user_id] = 'waiting_for_work'
                send_msg(vk, user_id, "✅ Данные сохранены! Вы в базе.\nТеперь отправьте текст работы или прикрепите файл.", keyboard=get_main_keyboard(user_id, ADMIN_IDS))

            elif user_states.get(user_id) == 'waiting_for_work':
                attachments = event.attachments
                if attachments or event.text:
                    student, _ = get_student(user_id)
                    student_info = student['name'] if student else "Данные не указаны"
                    
                    submissions = load_data(SUBMISSIONS_FILE, list)
                    new_id = len(submissions) + 1
                    
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
                    
                    send_msg(vk, user_id, "✅ Работа получена! Ожидайте проверки.", keyboard=get_main_keyboard(user_id, ADMIN_IDS))
                    for admin_id in ADMIN_IDS:
                        send_msg(vk, admin_id, f"🔔 Новая работа от {student_info}!\nНажмите 'Проверить работы'.", keyboard=get_main_keyboard(admin_id, ADMIN_IDS))
                    user_states[user_id] = None

            # --- ПРЕПОДАВАТЕЛЬСКИЕ КОМАНДЫ ---
            elif request == 'добавить задание' and user_id in ADMIN_IDS:
                user_states[user_id] = 'waiting_for_new_task'
                send_msg(vk, user_id, "Введите задание в формате:\nНазвание | Описание | Дедлайн\n\nПример:\nНаписать заметку | Про концерт | Пятница 18:00", keyboard=get_main_keyboard(user_id, ADMIN_IDS))

            elif user_states.get(user_id) == 'waiting_for_new_task' and user_id in ADMIN_IDS:
                parts = [p.strip() for p in event.text.split('|')]
                if len(parts) == 3:
                    tasks = load_data(TASKS_FILE, list)
                    tasks.append({"title": parts[0], "desc": parts[1], "deadline": parts[2]})
                    save_data(TASKS_FILE, tasks)
                    user_states[user_id] = None
                    send_msg(vk, user_id, "✅ Задание добавлено!", keyboard=get_main_keyboard(user_id, ADMIN_IDS))
                else:
                    send_msg(vk, user_id, "❌ Ошибка формата. Используйте два разделителя |", keyboard=get_main_keyboard(user_id, ADMIN_IDS))

            # НОВАЯ КОМАНДА: УДАЛЕНИЕ ЗАДАНИЯ
            elif request == 'удалить задание' and user_id in ADMIN_IDS:
                tasks = load_data(TASKS_FILE, list)
                if not tasks:
                    send_msg(vk, user_id, "📭 Список заданий пуст. Нечего удалять.", keyboard=get_main_keyboard(user_id, ADMIN_IDS))
                else:
                    text = "📋 Список всех заданий:\n\n"
                    for i, task in enumerate(tasks, 1):
                        text += f"{i}. {task['title']}\n"
                    text += "\nВведите номер задания, которое хотите удалить (или напишите 'Отмена'):"
                    
                    user_states[user_id] = 'waiting_for_delete_number'
                    send_msg(vk, user_id, text, keyboard=get_main_keyboard(user_id, ADMIN_IDS))

            # ОБРАБОТКА ВВОДА НОМЕРА ДЛЯ УДАЛЕНИЯ
            elif user_states.get(user_id) == 'waiting_for_delete_number' and user_id in ADMIN_IDS:
                if request == 'отмена':
                    user_states[user_id] = None
                    send_msg(vk, user_id, "Удаление отменено.", keyboard=get_main_keyboard(user_id, ADMIN_IDS))
                    continue

                try:
                    task_num = int(event.text.strip())
                    tasks = load_data(TASKS_FILE, list)
                    
                    if 1 <= task_num <= len(tasks):
                        deleted_task = tasks.pop(task_num - 1)
                        save_data(TASKS_FILE, tasks)
                        user_states[user_id] = None
                        send_msg(vk, user_id, f"✅ Задание '{deleted_task['title']}' успешно удалено!", keyboard=get_main_keyboard(user_id, ADMIN_IDS))
                    else:
                        send_msg(vk, user_id, f"❌ Ошибка: нет задания с номером {task_num}. Попробуйте еще раз или напишите 'Отмена'.")
                except ValueError:
                    send_msg(vk, user_id, "❌ Ошибка: нужно ввести номер (число). Попробуйте еще раз или напишите 'Отмена'.")

            elif request == 'проверить работы' and user_id in ADMIN_IDS:
                show_next_submission(vk, user_id, ADMIN_IDS)

            elif request in ['✅ оценить', '❌ отклонить', '✍️ только комментарий', '⏭ пропустить'] and user_id in ADMIN_IDS:
                state = user_states.get(user_id, {})
                if state.get('state') not in ['reviewing', 'waiting_for_feedback', 'waiting_for_grade']:
                    continue
                
                task_id = state['task_id']
                submissions = load_data(SUBMISSIONS_FILE, list)
                current_task = next((t for t in submissions if t['id'] == task_id), None)
                
                if not current_task:
                    show_next_submission(vk, user_id, ADMIN_IDS)
                    continue

                student_id = current_task['student_id']
                task_title = current_task['task_title']

                if request == '⏭ пропустить':
                    show_next_submission(vk, user_id, ADMIN_IDS, current_task_id=task_id)
                    
                elif request == '✅ оценить':
                    user_states[user_id] = {'state': 'waiting_for_grade', 'task_id': task_id}
                    send_msg(vk, user_id, "Введите оценку от 1 до 10 и (при желании) комментарий через пробел.\n\nПримеры:\n8\n10 Отличная работа!")
                    
                elif request == '❌ отклонить':
                    current_task['status'] = 'rejected'
                    save_data(SUBMISSIONS_FILE, submissions)
                    send_msg(vk, student_id, f"❌ Преподаватель проверил вашу работу!\nЗадание: {task_title}\nСтатус: Отклонено (нужна доработка).")
                    send_msg(vk, user_id, f"Работа №{task_id} отклонена.")
                    show_next_submission(vk, user_id, ADMIN_IDS)
                    
                elif request == '✍️ только комментарий':
                    user_states[user_id] = {'state': 'waiting_for_feedback', 'task_id': task_id}
                    send_msg(vk, user_id, "Напишите текст комментария/оценки для студента:")

            elif user_states.get(user_id, {}).get('state') == 'waiting_for_grade' and user_id in ADMIN_IDS:
                task_id = user_states[user_id]['task_id']
                submissions = load_data(SUBMISSIONS_FILE, list)
                current_task = next((t for t in submissions if t['id'] == task_id), None)
                
                if not current_task:
                    show_next_submission(vk, user_id, ADMIN_IDS)
                    continue

                text_parts = event.text.split(' ', 1)
                try:
                    points = int(text_parts[0])
                    if points < 1 or points > 10:
                        send_msg(vk, user_id, "❌ Ошибка: оценка должна быть от 1 до 10 баллов. Попробуйте еще раз (например: 8 Отлично).")
                        continue
                    comment = text_parts[1] if len(text_parts) > 1 else ""
                except ValueError:
                    send_msg(vk, user_id, "❌ Ошибка: оценка должна быть целым числом. Попробуйте еще раз (например: 8 Отлично).")
                    continue

                student_id = current_task['student_id']
                task_title = current_task['task_title']

                student, students = get_student(student_id)
                if student:
                    student['points'] += points
                    students[str(student_id)] = student
                    save_data(STUDENTS_FILE, students)
                    balance = student['points']
                else:
                    balance = "?"

                current_task['status'] = 'accepted'
                save_data(SUBMISSIONS_FILE, submissions)

                msg_to_student = f"✅ Преподаватель проверил вашу работу!\nЗадание: {task_title}\n\nВам начислено: {points} баллов! 🎉\nВаш баланс: {balance} баллов."
                if comment:
                    msg_to_student += f"\n\n💬 Комментарий преподавателя:\n{comment}"
                
                send_msg(vk, student_id, msg_to_student)
                send_msg(vk, user_id, f"✅ Оценка {points} баллов сохранена. Студент уведомлен.")
                show_next_submission(vk, user_id, ADMIN_IDS)

            elif user_states.get(user_id, {}).get('state') == 'waiting_for_feedback' and user_id in ADMIN_IDS:
                task_id = user_states[user_id]['task_id']
                submissions = load_data(SUBMISSIONS_FILE, list)
                current_task = next((t for t in submissions if t['id'] == task_id), None)
                
                if current_task:
                    student_id = current_task['student_id']
                    current_task['status'] = 'commented'
                    save_data(SUBMISSIONS_FILE, submissions)
                    
                    send_msg(vk, student_id, f"📩 Ответ от преподавателя:\n\n{event.text}")
                    send_msg(vk, user_id, f"✅ Комментарий отправлен студенту.")
                
                show_next_submission(vk, user_id, ADMIN_IDS)

            # --- ОБРАБОТКА НЕИЗВЕСТНЫХ КОМАНД ---
            else:
                if user_states.get(user_id) == 'waiting_for_work':
                     send_msg(vk, user_id, "Пожалуйста, отправьте текст работы или файл.", keyboard=get_main_keyboard(user_id, ADMIN_IDS))
                elif user_states.get(user_id) == 'waiting_for_name_group':
                     send_msg(vk, user_id, "Напишите ваше ФИО и группу (например: Иванов Иван, ИС-21).", keyboard=get_main_keyboard(user_id, ADMIN_IDS))
                else:
                     send_msg(vk, user_id, "Я не понимаю команду. Используйте кнопки 👇", keyboard=get_main_keyboard(user_id, ADMIN_IDS))

if __name__ == '__main__':
    main()