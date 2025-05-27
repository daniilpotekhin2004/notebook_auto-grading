import os
import glob
import re
import zipfile
import nbformat
import difflib
import pandas as pd
import logging
from fpdf import FPDF

# ---------------------------
# Настройка логирования
# ---------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ---------------------------
# Параметры
# ---------------------------
DIFF_MATCH_THRESHOLD = 0.05  # порог для выбора группы "unchanged", сравниваем с вопросом
TEMPLATE_NOTEBOOK = "Домашнее задание 4 (1).ipynb"  # шаблон (эталон) с вопросами
ZIP_FILE = "2023p4.zip"  # ZIP-архив со студенческими ноутбуками
OUTPUT_EXCEL = "Результаты_ДЗ4_lst.xlsx"
OUTPUT_PDF = "Отчет_ДЗ4.pdf"


# ---------------------------
# Функции очистки и агрегирования текста
# ---------------------------
def clean_text(text):
    """
    Очищает текст: удаляет строки с изображениями (markdown ![...](...)),
    приводит к нижнему регистру и убирает лишние пробелы.
    """
    lines = text.splitlines()
    cleaned = [line for line in lines if not re.search(r'!\[.*\]\(.*\)', line)]
    return "\n".join(cleaned).strip().lower()


def get_text_from_notebook(nb_path):
    """
    Агрегирует текст из всех ячеек ноутбука (если ячейка не пустая).
    Возвращает единый текст.
    """
    nb = nbformat.read(nb_path, as_version=4)
    texts = [cell.source.strip() for cell in nb.cells if cell.source.strip()]
    return "\n".join(texts)


def extract_blocks_from_notebook(nb_path):
    """
    Делит ноутбук на блоки по пустым кодовым ячейкам.
    Пустые кодовые ячейки считаются маркерами, между которыми объединяется текст.
    Возвращает список блоков – каждый блок считается потенциальным вопросом.
    """
    nb = nbformat.read(nb_path, as_version=4)
    cells = nb.cells
    marker_indices = [i for i, cell in enumerate(cells)
                      if cell.cell_type == 'code' and not cell.source.strip()]

    blocks = []
    prev_index = 0
    for marker in marker_indices:
        block_parts = [cell.source.strip() for cell in cells[prev_index:marker]]
        block_text = clean_text("\n".join(block_parts))
        if block_text:
            blocks.append(block_text)
        prev_index = marker + 1
    if prev_index < len(cells):
        block_parts = [cell.source.strip() for cell in cells[prev_index:]]
        block_text = clean_text("\n".join(block_parts))
        if block_text:
            blocks.append(block_text)
    return blocks


# ---------------------------
# Diff-подход: группировка строк из unified_diff
# ---------------------------
def compute_diff_groups(template_text, student_text):
    """
    Вычисляет unified diff между шаблонным текстом и текстом студента.
    Затем группирует подряд идущие строки одного типа:
      - 'unchanged': строки, начинающиеся с пробела (не изменённые)
      - 'new': строки, начинающиеся с '+' (новые, добавленные)
      - 'removed': строки, начинающиеся с '-' (удалённые)
    Возвращает список кортежей: (group_type, group_lines)
    """
    template_lines = template_text.splitlines()
    student_lines = student_text.splitlines()
    diff_lines = list(difflib.unified_diff(template_lines, student_lines, lineterm=""))

    groups = []
    current_type = None
    current_group = []
    for line in diff_lines:
        # Пропускаем служебные строки (заголовки, ханы)
        if line.startswith('---') or line.startswith('+++') or line.startswith('@@'):
            if current_group:
                groups.append((current_type, current_group))
                current_group = []
                current_type = None
            continue
        if line.startswith(' '):
            if current_type != 'unchanged':
                if current_group:
                    groups.append((current_type, current_group))
                    current_group = []
                current_type = 'unchanged'
            current_group.append(line[1:].rstrip())
        elif line.startswith('+'):
            if current_type != 'new':
                if current_group:
                    groups.append((current_type, current_group))
                    current_group = []
                current_type = 'new'
            current_group.append(line[1:].rstrip())
        elif line.startswith('-'):
            if current_type != 'removed':
                if current_group:
                    groups.append((current_type, current_group))
                    current_group = []
                current_type = 'removed'
            current_group.append(line[1:].rstrip())
    if current_group:
        groups.append((current_type, current_group))
    return groups


def merge_groups(groups):
    """
    Объединяет подряд идущие группы одного типа в одну.
    Например, если две подряд группы имеют тип 'unchanged' или 'new', они сливаются.
    """
    if not groups:
        return []
    merged = []
    current_type, current_lines = groups[0]
    for grp_type, grp_lines in groups[1:]:
        if grp_type == current_type:
            current_lines.extend(grp_lines)
        else:
            merged.append((current_type, current_lines))
            current_type, current_lines = grp_type, grp_lines
    merged.append((current_type, current_lines))
    return merged


# ---------------------------
# Diff-подход: выделение вопросов и ответов
# ---------------------------
def parse_student_notebook_diff(template_nb_path, student_nb_path):
    """
    Сравнивает текстовую версию шаблонного и студенческого ноутбуков.
    Получает diff-группы, объединяет подряд идущие группы одного типа.
    Для каждого шаблонного вопроса (блок, выделенный через extract_blocks_from_notebook)
    выбирается группа 'unchanged', наиболее похожая на вопрос (с использованием difflib.SequenceMatcher).
    Если коэффициент сходства >= порога, то следующие подряд группы с типом 'new'
    (если есть) объединяются и считаются ответом на данный вопрос.

    Возвращает два списка: template_questions и answers.
    Логгируются отладочные сведения.
    """
    template_text = get_text_from_notebook(template_nb_path)
    student_text = get_text_from_notebook(student_nb_path)

    raw_groups = compute_diff_groups(template_text, student_text)
    groups = merge_groups(raw_groups)

    logging.debug("Объединённые группы diff:")
    for idx, (grp_type, grp_lines) in enumerate(groups):
        logging.debug(f"Группа {idx + 1} ({grp_type}):")
        logging.debug("\n".join(grp_lines))
        logging.debug("-" * 40)

    template_questions = extract_blocks_from_notebook(template_nb_path)
    answers = []

    for q_idx, question in enumerate(template_questions):
        best_ratio = 0
        best_idx = None
        # Ищем среди групп типа 'unchanged' группу с максимальным коэффициентом сходства
        for idx, (grp_type, grp_lines) in enumerate(groups):
            if grp_type != 'unchanged':
                continue
            group_text = "\n".join(grp_lines)
            ratio = difflib.SequenceMatcher(None, question, group_text).ratio()
            logging.debug(f"Вопрос {q_idx + 1}: сравнение с группой {idx + 1} (unchanged), ratio = {ratio:.2f}")
            if ratio > best_ratio:
                best_ratio = ratio
                best_idx = idx
        if best_ratio >= DIFF_MATCH_THRESHOLD and best_idx is not None:
            # Собираем все подряд идущие группы 'new', начиная с best_idx+1
            answer_text_parts = []
            next_idx = best_idx + 1
            while next_idx < len(groups) and groups[next_idx][0] == 'new':
                answer_text_parts.extend(groups[next_idx][1])
                next_idx += 1
            answer_text = "\n".join(answer_text_parts).strip()
            logging.info(f"Вопрос {q_idx + 1} выбран с ratio = {best_ratio:.2f}. Ответ:\n{answer_text[:100]}...")
            answers.append(answer_text)
        else:
            logging.info(f"Для вопроса {q_idx + 1} не найдено подходящей группы (max ratio = {best_ratio:.2f}).")
            answers.append("")
    return template_questions, answers


# ---------------------------
# Распаковка ZIP-архива со студенческими ноутбуками
# ---------------------------
def unzip_student_notebooks(zip_path, extract_to="unzipped_students"):
    if not os.path.exists(extract_to):
        os.makedirs(extract_to)
    with zipfile.ZipFile(zip_path, 'r') as zf:
        zf.extractall(extract_to)
    return extract_to


# ---------------------------
# Функция генерации PDF-отчёта
# ---------------------------
# def generate_pdf_report(excel_file, output_pdf):
#     """
#     Читает Excel-файл с результатами и генерирует PDF-отчёт,
#     где для каждого вопроса выводится его текст (из шаблона)
#     и список ответов от студентов (с указанием имени файла).
#     """
#     df = pd.read_excel(excel_file)
#     # Определяем количество вопросов по столбцам, начинающимся с "Вопрос"
#     question_cols = [col for col in df.columns if col.startswith("Вопрос")]
#     num_questions = len(question_cols)
#
#     pdf = FPDF()
#     pdf.set_auto_page_break(auto=True, margin=15)
#     pdf.add_page()
#     pdf.set_font("Arial", "B", 16)
#     pdf.cell(0, 10, "Отчет по домашнему заданию", ln=True, align="C")
#     pdf.ln(10)
#
#     # Для каждого вопроса создаём отдельную страницу
#     for i in range(num_questions):
#         pdf.add_page()
#         pdf.set_font("Arial", "B", 14)
#         question_text = df[f"Вопрос {i + 1}"].iloc[0] if not pd.isna(df[f"Вопрос {i + 1}"].iloc[0]) else ""
#         pdf.multi_cell(0, 10, f"Вопрос {i + 1}:\n{question_text}", border=1)
#         pdf.ln(5)
#
#         pdf.set_font("Arial", "", 12)
#         answer_header = f"Ответ {i + 1}"
#         pdf.cell(0, 10, f"Ответы студентов:", ln=True)
#         pdf.ln(2)
#         for idx, row in df.iterrows():
#             file_name = row["Файл"]
#             answer_text = row[answer_header] if not pd.isna(row[answer_header]) else ""
#             pdf.multi_cell(0, 8, f"{file_name}: {answer_text}", border=1)
#             pdf.ln(1)
#
#     pdf.output(output_pdf)
#     logging.info(f"PDF-отчет сохранен в файле: {output_pdf}")
def convert_to_cp1251(text):
    """
    Преобразует строку в CP1251 с заменой символов, которые не поддерживаются.
    """
    try:
        return text.encode("cp1251", errors="replace").decode("cp1251")
    except Exception as e:
        return text
# ---------------------------
# Основная функция: обработка всех студенческих ноутбуков и формирование Excel и PDF
# ---------------------------
def main():
    # Распаковываем архив со студенческими ноутбуками
    student_dir = unzip_student_notebooks(ZIP_FILE)
    student_files = glob.glob(os.path.join(student_dir, "*.ipynb"))
    if not student_files:
        logging.error("Студенческие ноутбуки не найдены в архиве!")
        return

    # Получаем шаблонные вопросы (блоки) из эталонного ноутбука
    template_questions, _ = parse_student_notebook_diff(TEMPLATE_NOTEBOOK, TEMPLATE_NOTEBOOK)
    num_questions = len(template_questions)
    logging.info(f"Из шаблона извлечено вопросов: {num_questions}")

    # Формируем заголовки итоговой таблицы: "Файл", затем для каждого вопроса – "Вопрос i", "Ответ i"
    columns = ["Файл"]
    for i in range(1, num_questions + 1):
        columns.append(f"Вопрос {i}")
        columns.append(f"Ответ {i}")

    results = []
    for student_file in student_files:
        logging.info(f"Обрабатывается файл: {student_file}")
        tpl_q, answers = parse_student_notebook_diff(TEMPLATE_NOTEBOOK, student_file)
        row = {"Файл": os.path.basename(student_file)}
        for idx in range(num_questions):
            row[f"Вопрос {idx + 1}"] = tpl_q[idx] if idx < len(tpl_q) else ""
            row[f"Ответ {idx + 1}"] = answers[idx] if idx < len(answers) else ""
        results.append(row)

    df = pd.DataFrame(results, columns=columns)
    df.to_excel(OUTPUT_EXCEL, index=False)
    logging.info(f"Результаты сохранены в файле: {OUTPUT_EXCEL}")

    # Генерация PDF-отчёта
    #generate_pdf_report(OUTPUT_EXCEL, OUTPUT_PDF)


if __name__ == "__main__":
    main()
