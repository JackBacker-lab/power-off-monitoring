from telethon import TelegramClient, events
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
from telethon.tl.types import (
    MessageEntityBold, MessageEntityItalic, MessageEntityUnderline,
    MessageEntityStrike, MessageEntityCode, MessageEntityPre,
    MessageEntityTextUrl, MessageEntityMentionName
)
import re
from typing import TypedDict, TypeAlias, Dict, List


# Часовой ряд (48 получасов)
HalfHourRow: TypeAlias = List[int]

# Полный набор очередей в дне
RowsDict: TypeAlias = Dict[str, HalfHourRow]
# пример:
# {
#   "Черга 1.1": [0,1,0,...],
#   "Черга 1.2": [...],
# }

class Schedule(TypedDict):
    date: str
    rows: RowsDict


def escape_html(s: str) -> str:
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;"))
    
    

def apply_html_format(text: str, entities: list):
    if not entities:
        return escape_html(text)

    chars = list(escape_html(text))
    entities_sorted = sorted(entities, key=lambda e: e.offset + e.length, reverse=True)

    for e in entities_sorted:
        start = e.offset
        end = e.offset + e.length

        if isinstance(e, MessageEntityBold):
            chars.insert(end, "</b>")
            chars.insert(start, "<b>")

        elif isinstance(e, MessageEntityItalic):
            chars.insert(end, "</i>")
            chars.insert(start, "<i>")

        elif isinstance(e, MessageEntityUnderline):
            chars.insert(end, "</u>")
            chars.insert(start, "<u>")

        elif isinstance(e, MessageEntityStrike):
            chars.insert(end, "</s>")
            chars.insert(start, "<s>")

        elif isinstance(e, MessageEntityCode):
            chars.insert(end, "</code>")
            chars.insert(start, "<code>")

        elif isinstance(e, MessageEntityPre):
            chars.insert(end, "</pre>")
            chars.insert(start, "<pre>")

        elif isinstance(e, MessageEntityTextUrl):
            url = escape_html(e.url)
            part = "".join(chars[start:end])
            chars[start:end] = []
            chars.insert(start, f'<a href="{url}">{part}</a>')

        elif isinstance(e, MessageEntityMentionName):
            uid = e.user_id
            part = "".join(chars[start:end])
            chars[start:end] = []
            chars.insert(start, f'<a href="tg://user?id={uid}">{part}</a>')

    return "".join(chars)


def generate_schedule_table(schedule: Schedule, filename="schedule.png"):
    rows: RowsDict = schedule["rows"]
    date: str = schedule["date"]

    cell_width = 40 * 2
    cell_height = 60 * 2
    top_margin = 100 * 2
    left_margin = 70 * 2
    font_size = 13 * 2

    font_path = "fonts/DejaVuSans.ttf"
    font = ImageFont.truetype(font_path, font_size)
    header_font = ImageFont.truetype(font_path, 20 * 2)

    cols = len(next(iter(rows.values())))
    rows_count = len(rows)

    width = left_margin + cols*cell_width//2 + 20
    height = top_margin + rows_count*cell_height//2 - 20

    img = Image.new("RGB", (width, height), "white") # type: ignore
    draw = ImageDraw.Draw(img)

    if date is None:
        date = datetime.now().strftime("%A %d.%m.%Y")
    draw.text((width / 2 - 150, 10), date, fill="black", font=header_font)

    for i in range(24):
        hour_label = f"{i:02d}-{'%02d' % (i+1)}"
        draw.text((left_margin + i*cell_width + 5, top_margin - cell_height), hour_label, fill="black", font=font)

    for r_idx, (name, hours) in enumerate(rows.items()):
        y = top_margin - 70 + r_idx*cell_height/2
        draw.text((10, y + 14), name, fill="black", font=font)

        for c_idx, val in enumerate(hours):
            x0 = left_margin + c_idx*cell_width/2
            y0 = y
            x1 = x0 + cell_width / 2
            y1 = y0 + cell_height / 2

            color = (0, 120, 255) if val else (255, 230, 0)  # синий = отключено, желтый = свет есть
            draw.rectangle([x0, y0, x1, y1], fill=color, outline="black")

    img.save(filename)
    return filename


def time_to_index(raw_time: str) -> int:
    if not ":" in raw_time:
        return int(raw_time) * 2
    h, m = raw_time.split(":")
    return int(h) * 2 + 1 if int(m) <= 30 else int(h) * 2 + 2


def cut_after_last_queue(text: str) -> str:
    match = list(re.finditer(r"Черга\s*\d+\.\d+:.*", text))
    if not match:
        return text
    
    last = match[-1]
    return text[:last.end()]


def parse_schedule(raw: str):
    rows = {}
    header = raw
    idx = raw.find("Черга 1")
    if idx != -1:
        header = raw[:idx]
        raw = raw[idx:]
        
    raw = cut_after_last_queue(raw)
        
    d, m, y = header.split(".", 2)
    d = d[-2:]
    y = y[:4]
    date = ".".join((d, m, y))
        
    for line in raw.strip().split("\n"):
        name, intervals_raw = line.split(":", 1)
        intervals = intervals_raw.strip().split(",")

        hours = [0] * 48  # 0 = свет есть, 1 = отключение

        for interval in intervals:
            start, end = interval.strip().split("-")
            start = int(time_to_index(start))
            end = int(time_to_index(end))
            for h in range(start, end):
                hours[h] = 1

        rows[name.strip()] = hours
    return rows, header, date


def get_timestamp(idx: int) -> str:
    hours = idx // 2
    minutes = idx % 2
    hours_str = f"{hours:02d}"
    minutes_str = ":30" if minutes == 1 else ""
    return f"{hours_str}{minutes_str}"


def row_to_timestamps(row: list) -> str:
    timestamps = ""
    is_first = True
    for idx in range(len(row)):
        if row[idx] == 1:
            if idx == 0 or row[idx - 1] == 0:
                timestamp = get_timestamp(idx)
                if is_first:
                    timestamps += f"{timestamp}-"
                    is_first = False
                else:
                    timestamps += f", { timestamp}-"
            if idx == len(row) - 1 or row[idx + 1] == 0:
                timestamp = get_timestamp(idx + 1)
                timestamps += f"{timestamp}"
    return timestamps


def build_message(current_schedule: Schedule, header: str, prev_schedules: list[Schedule]) -> str:
    if header.endswith("\n"):
        header = header[:-1]
    message = header
    new_rows: RowsDict = {}
    old_rows: RowsDict = {}
    
    for schedule in prev_schedules:
        if schedule["date"] == current_schedule["date"]:
            old_rows = schedule["rows"]
            break
    new_rows = current_schedule["rows"]
    
    if not old_rows:
        for queue, row in new_rows.items():
            timestamps = row_to_timestamps(row)
            message = message + "\n" + queue + ": " + timestamps
    else:
        for queue, row in new_rows.items():
            if row != old_rows[queue]:
                timestamps = row_to_timestamps(old_rows[queue])
                message = message + "\n" + queue + " (до змін): " + timestamps
                timestamps = row_to_timestamps(row)
                message = message + "\n" + queue + " (дійсний): " + timestamps
                
    print(message)
    return message


def remove_markdown_stars(text: str) -> str:
    return re.sub(r"\*", "", text)
        

api_id = 25141343
api_hash = "73a17ccc41bb711c547be190bb9279b9"

client = TelegramClient('bot', api_id, api_hash).start(bot_token="8341726798:AAHkK83q6pe9smi4eydU65QG3F-1N8Sna20")
    
prev_schedules: list[Schedule] = []

@client.on(events.NewMessage(chats="https://t.me/SvitloSvitlovodskohoRaionu"))
async def handler(event):
    global prev_schedules
    
    message_text = event.message.text
    message_text = remove_markdown_stars(message_text)
    entities = event.message.entities or []
    print("NEW MESSAGE:", message_text)
    
    rows: RowsDict
    header: str
    date: str
    rows, header, date = parse_schedule(message_text)
    schedule: Schedule = {
        "date": date,
        "rows": rows
    }
    
    generate_schedule_table(schedule, "schedule.png")
    
    message: str = build_message(schedule, header, prev_schedules)
    message_html: str = apply_html_format(message, entities)
    
    for idx, old_schedule in enumerate(prev_schedules):
        if old_schedule["date"] == date:
            prev_schedules[idx] = schedule
            break
    else:
        prev_schedules.append(schedule)
    
    await client.send_file(
        'https://t.me/test12434534132432',
        file='schedule.png',
        caption=f"{message_html}",
        parse_mode='html'
    )

client.start()
client.run_until_disconnected()





