import { DatabaseSync } from "node:sqlite";
import { mkdirSync } from "node:fs";
import { cfg } from "../config.js";

function utcNow(): string {
  return new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
}

let db: DatabaseSync | null = null;

export function initConversationsDb(): void {
  mkdirSync(cfg.conversationsDataDir, { recursive: true });
  const path = `${cfg.conversationsDataDir}/agent.db`;
  db = new DatabaseSync(path);
  db.exec(`
    CREATE TABLE IF NOT EXISTS conversations (
      id TEXT PRIMARY KEY,
      device_id TEXT NOT NULL DEFAULT '',
      title TEXT NOT NULL DEFAULT 'New conversation',
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS messages (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      conversation_id TEXT NOT NULL,
      role TEXT NOT NULL,
      content TEXT NOT NULL,
      meta TEXT,
      created_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages(conversation_id, id ASC);
    CREATE INDEX IF NOT EXISTS idx_conv_device_updated ON conversations(device_id, updated_at DESC);
  `);
}

function getDb(): DatabaseSync {
  if (!db) initConversationsDb();
  return db!;
}

export function createConversation(deviceId: string, title = "New conversation") {
  const id = crypto.randomUUID();
  const now = utcNow();
  const t = (title || "New conversation").trim().slice(0, 80) || "New conversation";
  getDb()
    .prepare(
      "INSERT INTO conversations (id, device_id, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
    )
    .run(id, deviceId, t, now, now);
  return { id, title: t, created_at: now, updated_at: now };
}

export function listConversations(deviceId: string, limit = 50) {
  return getDb()
    .prepare(
      "SELECT id, title, created_at, updated_at FROM conversations WHERE device_id = ? ORDER BY updated_at DESC LIMIT ?",
    )
    .all(deviceId, limit) as Array<Record<string, string>>;
}

export function belongsToDevice(conversationId: string, deviceId: string): boolean {
  const row = getDb()
    .prepare("SELECT 1 AS ok FROM conversations WHERE id = ? AND device_id = ?")
    .get(conversationId, deviceId) as { ok: number } | undefined;
  return Boolean(row?.ok);
}

export function getConversation(conversationId: string, deviceId: string) {
  const conv = getDb()
    .prepare("SELECT id, title, created_at, updated_at FROM conversations WHERE id = ? AND device_id = ?")
    .get(conversationId, deviceId) as Record<string, string> | undefined;
  if (!conv) return null;
  const messages = getDb()
    .prepare(
      "SELECT id, role, content, meta, created_at FROM messages WHERE conversation_id = ? ORDER BY id ASC",
    )
    .all(conversationId) as Array<Record<string, unknown>>;
  return {
    ...conv,
    messages: messages.map((m) => ({
      ...m,
      meta: m.meta ? JSON.parse(String(m.meta)) : null,
    })),
  };
}

export function deleteConversation(conversationId: string, deviceId: string): boolean {
  const res = getDb()
    .prepare("DELETE FROM conversations WHERE id = ? AND device_id = ?")
    .run(conversationId, deviceId);
  return Number(res.changes) > 0;
}

export function addMessage(
  conversationId: string,
  role: string,
  content: string,
  meta?: Record<string, unknown> | null,
) {
  const now = utcNow();
  getDb()
    .prepare("INSERT INTO messages (conversation_id, role, content, meta, created_at) VALUES (?, ?, ?, ?, ?)")
    .run(conversationId, role, content, meta ? JSON.stringify(meta) : null, now);
  getDb().prepare("UPDATE conversations SET updated_at = ? WHERE id = ?").run(now, conversationId);
}

export function updateTitle(conversationId: string, title: string) {
  getDb()
    .prepare("UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?")
    .run(title.slice(0, 80), utcNow(), conversationId);
}

export function titleFromMessage(msg: string): string {
  const t = (msg || "").replace(/\s+/g, " ").trim();
  return t.length > 60 ? `${t.slice(0, 57)}…` : t || "New conversation";
}
