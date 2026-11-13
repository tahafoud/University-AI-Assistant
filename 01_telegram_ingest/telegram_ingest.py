"""
telegram_ingest.py - Monitor a Telegram channel, download media, OCR images,
clean Arabic text, store everything in SQLite and export announcements.json
(which the Flutter app will sync from in phase 3).

First run asks for your phone number + login code (creates a session file).
Run:  python telegram_ingest.py
"""
import asyncio
import hashlib
import json
import logging
import os
import re
import sqlite3
from datetime import timezone
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError

from arabic_text import clean_arabic_text
from ocr_engine import ArabicOCR

load_dotenv()
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("ingest")

API_ID = int(os.environ["TG_API_ID"])
API_HASH = os.environ["TG_API_HASH"]
CHANNEL = os.environ["TG_CHANNEL"]
BACKFILL_LIMIT = int(os.getenv("TG_BACKFILL_LIMIT", "200"))
MAX_MEDIA_BYTES = int(os.getenv("TG_MAX_MEDIA_MB", "25")) * 1024 * 1024
DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
MEDIA_DIR = DATA_DIR / "media"
DB_PATH = DATA_DIR / "announcements.db"
JSON_PATH = DATA_DIR / "announcements.json"
EXPORT_LIMIT = 500

SPREADSHEET_EXT = {".xlsx", ".xls", ".csv"}


# ----------------------------------------------------------------------
# Storage
# ----------------------------------------------------------------------
class Store:
    def __init__(self, path: Path):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS announcements (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                channel       TEXT NOT NULL,
                message_id    INTEGER NOT NULL,
                date_utc      TEXT NOT NULL,
                text_raw      TEXT,
                ocr_text      TEXT,
                text_display  TEXT,
                text_search   TEXT,
                media_type    TEXT,
                media_path    TEXT,
                file_name     TEXT,
                content_hash  TEXT,
                is_deleted    INTEGER DEFAULT 0,
                updated_at    TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(channel, message_id)
            )""")
        self.conn.commit()

    def last_message_id(self, channel: str) -> int:
        row = self.conn.execute(
            "SELECT MAX(message_id) m FROM announcements WHERE channel=?",
            (channel,)).fetchone()
        return row["m"] or 0

    def get_media(self, channel: str, message_id: int):
        return self.conn.execute(
            "SELECT media_path, ocr_text FROM announcements "
            "WHERE channel=? AND message_id=?", (channel, message_id)).fetchone()

    def upsert(self, r: dict):
        self.conn.execute("""
            INSERT INTO announcements
              (channel, message_id, date_utc, text_raw, ocr_text, text_display,
               text_search, media_type, media_path, file_name, content_hash,
               is_deleted)
            VALUES (:channel,:message_id,:date_utc,:text_raw,:ocr_text,
                    :text_display,:text_search,:media_type,:media_path,
                    :file_name,:content_hash,0)
            ON CONFLICT(channel, message_id) DO UPDATE SET
              text_raw=excluded.text_raw, ocr_text=excluded.ocr_text,
              text_display=excluded.text_display, text_search=excluded.text_search,
              media_type=excluded.media_type, media_path=excluded.media_path,
              file_name=excluded.file_name, content_hash=excluded.content_hash,
              is_deleted=0, updated_at=CURRENT_TIMESTAMP
        """, r)
        self.conn.commit()

    def mark_deleted(self, channel: str, ids):
        self.conn.executemany(
            "UPDATE announcements SET is_deleted=1, updated_at=CURRENT_TIMESTAMP "
            "WHERE channel=? AND message_id=?", [(channel, i) for i in ids])
        self.conn.commit()

    def export_json(self, path: Path, channel: str, limit: int = EXPORT_LIMIT):
        rows = self.conn.execute(
            "SELECT message_id, date_utc, text_display, media_type, media_path, "
            "file_name, content_hash FROM announcements "
            "WHERE channel=? AND is_deleted=0 AND "
            "      (TRIM(COALESCE(text_display,''))<>'' OR media_path IS NOT NULL) "
            "ORDER BY message_id DESC LIMIT ?", (channel, limit)).fetchall()
        payload = {
            "channel": channel,
            "count": len(rows),
            "items": [{
                "id": r["message_id"],
                "date": r["date_utc"],
                "text": r["text_display"],
                "media_type": r["media_type"],
                "media": r["media_path"],
                "file_name": r["file_name"],
                "hash": r["content_hash"],
            } for r in rows],
        }
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        tmp.replace(path)  # atomic: readers never see a half-written file


# ----------------------------------------------------------------------
# Message processing
# ----------------------------------------------------------------------
def _safe_name(name: str) -> str:
    return re.sub(r"[^\w.\-\u0600-\u06FF]+", "_", name)[:80]


def _classify(msg) -> str | None:
    if not msg.media:
        return None
    if msg.photo:
        return "photo"
    if msg.document and msg.file:
        mime = (msg.file.mime_type or "").lower()
        ext = (msg.file.ext or "").lower()
        if mime.startswith("image/"):
            return "image"
        if mime == "application/pdf" or ext == ".pdf":
            return "pdf"
        if ext in SPREADSHEET_EXT:
            return "spreadsheet"
        return "document"
    return None  # polls, web previews, etc.


class Ingestor:
    def __init__(self, client: TelegramClient, store: Store, ocr: ArabicOCR,
                 channel_key: str):
        self.client, self.store, self.ocr = client, store, ocr
        self.channel_key = channel_key
        self._lock = asyncio.Lock()  # one message at a time (OCR is heavy)

    async def handle(self, msg):
        async with self._lock:
            for attempt in range(3):
                try:
                    await self._process(msg)
                    self.store.export_json(JSON_PATH, self.channel_key)
                    return
                except FloodWaitError as e:
                    log.warning("FloodWait %ss", e.seconds)
                    await asyncio.sleep(e.seconds + 1)
                except Exception:  # noqa: BLE001
                    log.exception("Failed on message %s (attempt %d)", msg.id,
                                  attempt + 1)
                    await asyncio.sleep(2)

    async def _process(self, msg):
        text_raw = msg.message or ""
        media_type = _classify(msg)
        media_path = file_name = None
        ocr_text = ""

        if media_type:
            file_name = msg.file.name if msg.file and msg.file.name else None
            size = (msg.file.size or 0) if msg.file else 0
            if size and size > MAX_MEDIA_BYTES:
                log.info("Skip large media (%.1f MB) in msg %s",
                         size / 1e6, msg.id)
            else:
                prev = self.store.get_media(self.channel_key, msg.id)
                if prev and prev["media_path"] and Path(prev["media_path"]).exists():
                    # Edited message: reuse the already-downloaded file + OCR
                    media_path, ocr_text = prev["media_path"], prev["ocr_text"] or ""
                else:
                    stem = f"{msg.id}_{_safe_name(file_name)}" if file_name else str(msg.id)
                    media_path = await msg.download_media(
                        file=str(MEDIA_DIR / stem))
                    if media_type in ("photo", "image") and media_path:
                        log.info("OCR on message %s ...", msg.id)
                        ocr_text = await asyncio.to_thread(
                            self.ocr.read_file, media_path)

        combined = "\n".join(t for t in (text_raw, ocr_text) if t.strip())
        text_display = clean_arabic_text(combined, "display")
        text_search = clean_arabic_text(combined, "nlp")

        self.store.upsert({
            "channel": self.channel_key,
            "message_id": msg.id,
            "date_utc": msg.date.astimezone(timezone.utc).isoformat(),
            "text_raw": text_raw,
            "ocr_text": ocr_text,
            "text_display": text_display,
            "text_search": text_search,
            "media_type": media_type,
            "media_path": media_path,
            "file_name": file_name,
            "content_hash": hashlib.sha1(
                (text_display + str(media_path)).encode("utf-8")).hexdigest(),
        })
        log.info("Saved message %s (%s, %d chars)", msg.id,
                 media_type or "text", len(text_display))


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
async def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)

    store = Store(DB_PATH)
    ocr = ArabicOCR(gpu=False)
    client = TelegramClient(str(DATA_DIR / "tg_session"), API_ID, API_HASH)
    await client.start()  # interactive login on first run

    entity = await client.get_entity(CHANNEL)
    channel_key = str(getattr(entity, "username", None) or entity.id)
    ing = Ingestor(client, store, ocr, channel_key)

    # ---- 1) Backfill / catch-up ----
    last_id = store.last_message_id(channel_key)
    if last_id == 0:
        log.info("First run: fetching last %d messages", BACKFILL_LIMIT)
        msgs = [m async for m in client.iter_messages(entity, limit=BACKFILL_LIMIT)]
        msgs.reverse()  # oldest -> newest
    else:
        log.info("Catching up after message id %d", last_id)
        msgs = [m async for m in client.iter_messages(entity, min_id=last_id,
                                                      reverse=True)]
    for m in msgs:
        if m.message or m.media:  # skip service messages
            await ing.handle(m)
    log.info("Backfill done (%d messages)", len(msgs))

    # ---- 2) Live monitoring ----
    @client.on(events.NewMessage(chats=entity))
    async def _new(event):
        await ing.handle(event.message)

    @client.on(events.MessageEdited(chats=entity))
    async def _edited(event):
        await ing.handle(event.message)

    @client.on(events.MessageDeleted(chats=entity))
    async def _deleted(event):
        store.mark_deleted(channel_key, event.deleted_ids)
        store.export_json(JSON_PATH, channel_key)

    log.info("Listening to %s ... (Ctrl+C to stop)", channel_key)
    await client.run_until_disconnected()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
