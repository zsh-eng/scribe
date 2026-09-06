import Database from 'better-sqlite3';
import path from 'path';

// Connect to SQLite database
const dbPath = process.env.PARLIAMENT_DB_PATH || path.join(process.cwd(), '..', 'data', 'parliament.db');
const db = new Database(dbPath, { readonly: true });

// Enable WAL mode for better read performance
db.pragma('journal_mode = WAL');

export default db;
