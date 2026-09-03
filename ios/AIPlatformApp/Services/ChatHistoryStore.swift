import Foundation
import SQLite3

public struct StoredMessagePage: Sendable {
    public let messages: [ChatMessage]
    public let hasOlder: Bool
    public let hasNewer: Bool
}

public enum SessionLifecycleStatus: String, Codable, CaseIterable, Sendable {
    case active, archived, trashed
}

public struct StoredSessionSummary: Sendable {
    public let id: String
    public let title: String
    public let updatedAt: Date
    public let messageCount: Int
    public let agentId: String
    public let agentName: String
    public let topic: TopicSessionMetadata?
    public let lifecycleStatus: SessionLifecycleStatus
    public let organizedAt: Date?
    public let archivedAt: Date?
    public let trashedAt: Date?
}

/// Indexed local history. A recursive connection lock serializes complete SQLite
/// transactions across MainActor reads and detached persistence writes.
public final class ChatHistoryStore: @unchecked Sendable {
    public static let pageMessageLimit = 24
    public static let pageCharacterLimit = 80_000

    private var db: OpaquePointer?
    private let legacyDirectory: URL
    private let connectionLock = NSRecursiveLock()
    private static let transient = unsafeBitCast(-1, to: sqlite3_destructor_type.self)
    private static let encoder: JSONEncoder = { let x = JSONEncoder(); x.dateEncodingStrategy = .iso8601; return x }()
    private static let decoder: JSONDecoder = { let x = JSONDecoder(); x.dateDecodingStrategy = .iso8601; return x }()

    public init(databaseURL: URL? = nil, legacyDirectory: URL? = nil, performLegacyMigration: Bool = true) throws {
        let fm = FileManager.default
        let docs = fm.urls(for: .documentDirectory, in: .userDomainMask).first ?? fm.temporaryDirectory
        let url = databaseURL ?? docs.appendingPathComponent("ChatHistory/history-v2.sqlite")
        self.legacyDirectory = legacyDirectory ?? docs.appendingPathComponent("Sessions", isDirectory: true)
        try fm.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        let flags = SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE | SQLITE_OPEN_FULLMUTEX
        guard sqlite3_open_v2(url.path, &db, flags, nil) == SQLITE_OK else { throw error("open") }
        try exec("PRAGMA foreign_keys=ON"); try exec("PRAGMA journal_mode=WAL"); try exec("PRAGMA synchronous=NORMAL"); try exec("PRAGMA busy_timeout=100")
        try schema()
        if performLegacyMigration { try migrateLegacySessions() }
    }

    deinit { sqlite3_close(db) }

    public func summaries() throws -> [StoredSessionSummary] {
        try query("SELECT id,title,updated_at,message_count,agent_id,agent_name,topic_payload,lifecycle_status,organized_at,archived_at,trashed_at FROM sessions ORDER BY updated_at DESC") { s in
            StoredSessionSummary(
                id: text(s, 0), title: text(s, 1),
                updatedAt: Date(timeIntervalSince1970: sqlite3_column_double(s, 2)),
                messageCount: Int(sqlite3_column_int64(s, 3)), agentId: text(s, 4),
                agentName: text(s, 5), topic: decodeTopic(s, 6),
                lifecycleStatus: SessionLifecycleStatus(rawValue: text(s, 7)) ?? .active,
                organizedAt: optionalDate(s, 8), archivedAt: optionalDate(s, 9),
                trashedAt: optionalDate(s, 10)
            )
        }
    }

    public func summary(sessionId: String) throws -> StoredSessionSummary? {
        try query(
            "SELECT id,title,updated_at,message_count,agent_id,agent_name,topic_payload,lifecycle_status,organized_at,archived_at,trashed_at FROM sessions WHERE id=? LIMIT 1",
            { bind(sessionId, $0, 1) }
        ) { s in
            StoredSessionSummary(
                id: text(s, 0), title: text(s, 1),
                updatedAt: Date(timeIntervalSince1970: sqlite3_column_double(s, 2)),
                messageCount: Int(sqlite3_column_int64(s, 3)),
                agentId: text(s, 4), agentName: text(s, 5), topic: decodeTopic(s, 6),
                lifecycleStatus: SessionLifecycleStatus(rawValue: text(s, 7)) ?? .active,
                organizedAt: optionalDate(s, 8), archivedAt: optionalDate(s, 9),
                trashedAt: optionalDate(s, 10)
            )
        }.first
    }

    public func createSession(id: String, agentId: String, agentName: String) throws {
        try run("INSERT OR IGNORE INTO sessions(id,title,updated_at,message_count,next_sequence,agent_id,agent_name) VALUES(?,?,?,?,?,?,?)") { s in
            bind(id,s,1); bind("新会话",s,2); sqlite3_bind_double(s,3,Date().timeIntervalSince1970)
            sqlite3_bind_int64(s,4,0); sqlite3_bind_int64(s,5,0); bind(agentId,s,6); bind(agentName,s,7)
        }
    }

    public func updateTopic(_ topic: TopicSessionMetadata) throws {
        let payload = try Self.encoder.encode(topic)
        try run("UPDATE sessions SET topic_payload=?,updated_at=? WHERE id=?") { s in
            bind(payload,s,1); sqlite3_bind_double(s,2,Date().timeIntervalSince1970); bind(topic.sessionId,s,3)
        }
    }


    public func latest(sessionId: String) throws -> StoredMessagePage { try page(sessionId, clause: "", anchor: nil, descending: true) }
    public func before(sessionId: String, messageId: String) throws -> StoredMessagePage {
        guard let n = try sequence(sessionId, messageId) else { return try latest(sessionId: sessionId) }
        return try page(sessionId, clause: "AND sequence<?", anchor: n, descending: true)
    }
    public func after(sessionId: String, messageId: String) throws -> StoredMessagePage {
        guard let n = try sequence(sessionId, messageId) else { return try latest(sessionId: sessionId) }
        return try page(sessionId, clause: "AND sequence>?", anchor: n, descending: false)
    }

    @discardableResult public func upsert(_ messages: [ChatMessage], sessionId: String) throws -> Int {
        guard !messages.isEmpty else { return try count(sessionId) }
        try transaction {
            try upsertRows(messages, sessionId: sessionId)
        }
        return try count(sessionId)
    }

    public func message(sessionId: String, id: String) throws -> ChatMessage? {
        try query("SELECT payload FROM messages WHERE session_id=? AND message_id=? LIMIT 1", { s in bind(sessionId,s,1); bind(id,s,2) }) { decode($0,0,sessionId) }.first
    }

    public func previousUser(sessionId: String, before messageId: String) throws -> ChatMessage? {
        guard let n = try sequence(sessionId,messageId) else { return nil }
        return try query("SELECT payload FROM messages WHERE session_id=? AND sequence<? AND role=? ORDER BY sequence DESC LIMIT 1", { s in bind(sessionId,s,1); sqlite3_bind_int64(s,2,n); bind(MessageRole.user.rawValue,s,3) }) { decode($0,0,sessionId) }.first
    }

    public func contextMessages(
        sessionId: String, maxMessages: Int = 200, maxCharacters: Int = 120_000
    ) throws -> (messages: [ChatMessage], truncated: Bool) {
        var rows = try query(
            "SELECT payload FROM messages WHERE session_id=? ORDER BY sequence DESC LIMIT ?",
            { s in bind(sessionId, s, 1); sqlite3_bind_int(s, 2, Int32(maxMessages + 1)) }
        ) { decode($0, 0, sessionId) }
        let exceededCount = rows.count > maxMessages
        if exceededCount { rows = Array(rows.prefix(maxMessages)) }
        var kept: [ChatMessage] = []
        var characters = 0
        for message in rows {
            let cost = message.content.count
            if !kept.isEmpty && characters + cost > maxCharacters { break }
            kept.append(message)
            characters += cost
        }
        let truncated = exceededCount || kept.count < rows.count
        return (Array(kept.reversed()), truncated)
    }

    public func truncate(sessionId: String, from messageId: String) throws {
        guard let n = try sequence(sessionId,messageId) else { return }
        try transaction { try run("DELETE FROM messages WHERE session_id=? AND sequence>=?") { s in bind(sessionId,s,1); sqlite3_bind_int64(s,2,n) }; try refreshCount(sessionId) }
    }

    public func clear(_ id: String) throws {
        try transaction {
            try run("DELETE FROM messages WHERE session_id=?") { bind(id,$0,1) }
            try run("UPDATE sessions SET title='新会话',message_count=0,next_sequence=0,updated_at=? WHERE id=?") { s in sqlite3_bind_double(s,1,Date().timeIntervalSince1970); bind(id,s,2) }
        }
    }
    public func delete(_ id: String) throws { try run("DELETE FROM sessions WHERE id=?") { bind(id,$0,1) } }
    public func setLifecycle(_ status: SessionLifecycleStatus, sessionId: String) throws {
        let now = Date().timeIntervalSince1970
        try run("UPDATE sessions SET lifecycle_status=?,archived_at=?,trashed_at=? WHERE id=?") { s in
            bind(status.rawValue, s, 1)
            if status == .archived { sqlite3_bind_double(s, 2, now) } else { sqlite3_bind_null(s, 2) }
            if status == .trashed { sqlite3_bind_double(s, 3, now) } else { sqlite3_bind_null(s, 3) }
            bind(sessionId, s, 4)
        }
    }
    public func markOrganized(_ sessionIds: [String]) throws {
        let now = Date().timeIntervalSince1970
        try transaction {
            for id in sessionIds {
                try run("UPDATE sessions SET organized_at=? WHERE id=?") { s in
                    sqlite3_bind_double(s, 1, now); bind(id, s, 2)
                }
            }
        }
    }
    public func linkOrganizationSources(organizerSessionId: String, sourceSessionIds: [String]) throws {
        try transaction {
            try run("DELETE FROM session_organization_sources WHERE organizer_session_id=?") { bind(organizerSessionId, $0, 1) }
            for sourceId in sourceSessionIds where sourceId != organizerSessionId {
                try run("INSERT OR IGNORE INTO session_organization_sources(organizer_session_id,source_session_id) VALUES(?,?)") { s in
                    bind(organizerSessionId, s, 1); bind(sourceId, s, 2)
                }
            }
        }
    }
    public func organizationSources(organizerSessionId: String) throws -> [String] {
        try query("SELECT source_session_id FROM session_organization_sources WHERE organizer_session_id=? ORDER BY source_session_id", { bind(organizerSessionId, $0, 1) }) { text($0, 0) }
    }
    public func count(_ id: String) throws -> Int { Int(try int64("SELECT message_count FROM sessions WHERE id=?", { bind(id,$0,1) })) }

    // Async application-facing API. The synchronous primitives remain available for the MainActor cache.
    public func loadLatestPage(sessionId: String) async throws -> StoredMessagePage { try latest(sessionId: sessionId) }
    public func loadPage(before messageId: String, sessionId: String) async throws -> StoredMessagePage { try before(sessionId: sessionId, messageId: messageId) }
    public func loadPage(after messageId: String, sessionId: String) async throws -> StoredMessagePage { try after(sessionId: sessionId, messageId: messageId) }
    @discardableResult public func appendMessages(_ messages: [ChatMessage], sessionId: String) async throws -> Int { try upsert(messages, sessionId: sessionId) }
    @discardableResult public func upsertMessages(_ messages: [ChatMessage], sessionId: String) async throws -> Int { try upsert(messages, sessionId: sessionId) }
    public func truncateMessages(from messageId: String, sessionId: String) async throws { try truncate(sessionId: sessionId, from: messageId) }
    public func clearSession(_ id: String) async throws { try clear(id) }
    public func deleteSession(_ id: String) async throws { try delete(id) }
    public func messageCount(_ id: String) async throws -> Int { try count(id) }
    public func previousUserMessage(before messageId: String, sessionId: String) async throws -> ChatMessage? { try previousUser(sessionId: sessionId, before: messageId) }

    private func page(_ id: String, clause: String, anchor: Int64?, descending: Bool) throws -> StoredMessagePage {
        let order = descending ? "DESC" : "ASC"
        var rows: [(Int64,ChatMessage)] = try query("SELECT sequence,payload FROM messages WHERE session_id=? \(clause) ORDER BY sequence \(order) LIMIT ?", { s in
            bind(id,s,1); var i:Int32=2; if let anchor { sqlite3_bind_int64(s,i,anchor); i += 1 }; sqlite3_bind_int(s,i,Int32(Self.pageMessageLimit))
        }) { s in (sqlite3_column_int64(s,0),decode(s,1,id)) }
        if descending { rows.reverse() }
        var kept:[(Int64,ChatMessage)] = []; var chars=0
        let candidates = descending ? Array(rows.reversed()) : rows
        for row in candidates { let cost=row.1.content.count; if !kept.isEmpty && chars+cost>Self.pageCharacterLimit { break }; kept.append(row); chars += cost }
        if descending { kept.reverse() }
        rows = kept
        guard let lo=rows.first?.0, let hi=rows.last?.0 else { return StoredMessagePage(messages:[],hasOlder:false,hasNewer:false) }
        return StoredMessagePage(messages:rows.map(\.1), hasOlder:try exists(id,"sequence<?",lo), hasNewer:try exists(id,"sequence>?",hi))
    }

    private func schema() throws {
        try exec("CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY,title TEXT NOT NULL,updated_at REAL NOT NULL,message_count INTEGER NOT NULL DEFAULT 0,next_sequence INTEGER NOT NULL DEFAULT 0,agent_id TEXT NOT NULL,agent_name TEXT NOT NULL)")
        if !tableColumns("sessions").contains("topic_payload") {
            try exec("ALTER TABLE sessions ADD COLUMN topic_payload BLOB")
        }
        if !tableColumns("sessions").contains("lifecycle_status") { try exec("ALTER TABLE sessions ADD COLUMN lifecycle_status TEXT NOT NULL DEFAULT 'active'") }
        if !tableColumns("sessions").contains("organized_at") { try exec("ALTER TABLE sessions ADD COLUMN organized_at REAL") }
        if !tableColumns("sessions").contains("archived_at") { try exec("ALTER TABLE sessions ADD COLUMN archived_at REAL") }
        if !tableColumns("sessions").contains("trashed_at") { try exec("ALTER TABLE sessions ADD COLUMN trashed_at REAL") }
        try exec("CREATE TABLE IF NOT EXISTS messages(session_id TEXT NOT NULL,sequence INTEGER NOT NULL,message_id TEXT NOT NULL,role TEXT NOT NULL,payload BLOB NOT NULL,PRIMARY KEY(session_id,sequence),UNIQUE(session_id,message_id),FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE)")
        try exec("CREATE INDEX IF NOT EXISTS idx_messages_lookup ON messages(session_id,message_id)")
        try exec("CREATE INDEX IF NOT EXISTS idx_sessions_lifecycle ON sessions(lifecycle_status,updated_at DESC)")
        try exec("CREATE TABLE IF NOT EXISTS session_organization_sources(organizer_session_id TEXT NOT NULL,source_session_id TEXT NOT NULL,PRIMARY KEY(organizer_session_id,source_session_id),FOREIGN KEY(organizer_session_id) REFERENCES sessions(id) ON DELETE CASCADE,FOREIGN KEY(source_session_id) REFERENCES sessions(id) ON DELETE CASCADE)")
    }

    private func tableColumns(_ table: String) -> Set<String> {
        Set((try? query("PRAGMA table_info(\(table))") { text($0, 1) }) ?? [])
    }

    private func decodeTopic(_ statement: OpaquePointer?, _ column: Int32) -> TopicSessionMetadata? {
        guard sqlite3_column_type(statement, column) != SQLITE_NULL else { return nil }
        let count = Int(sqlite3_column_bytes(statement, column))
        guard let bytes = sqlite3_column_blob(statement, column), count > 0 else { return nil }
        return try? Self.decoder.decode(TopicSessionMetadata.self, from: Data(bytes: bytes, count: count))
    }

    public func migrateLegacySessions() throws {
        let fm=FileManager.default; guard let files=try? fm.contentsOfDirectory(at:legacyDirectory,includingPropertiesForKeys:nil).filter({$0.pathExtension=="json"}) else{return}
        for file in files {
            do {
                let record=try Self.decoder.decode(SessionRecord.self,from:Data(contentsOf:file))
                let backup=file.deletingPathExtension().appendingPathExtension("json.v1-backup")
                if try int64("SELECT EXISTS(SELECT 1 FROM sessions WHERE id=?)", { bind(record.id,$0,1) }) != 0 {
                    let ids = try query("SELECT message_id FROM messages WHERE session_id=? ORDER BY sequence", { bind(record.id,$0,1) }) { text($0,0) }
                    if try count(record.id) == record.messages.count,
                       ids.first == record.messages.first?.id,
                       ids.last == record.messages.last?.id,
                       !fm.fileExists(atPath: backup.path) {
                        try fm.moveItem(at:file,to:backup)
                    }
                    continue
                }
                try transaction {
                    try createSession(id:record.id,agentId:record.agentId ?? "main_agent",agentName:record.agentName ?? "Main 智能编排")
                    try upsertRows(record.messages.map { $0.toChatMessage(sessionId:record.id) },sessionId:record.id)
                    try run("UPDATE sessions SET title=?,updated_at=? WHERE id=?") { s in bind(record.title,s,1);sqlite3_bind_double(s,2,record.updatedAt.timeIntervalSince1970);bind(record.id,s,3) }
                    guard try count(record.id)==record.messages.count else { throw error("migration verification") }
                    let ids = try query("SELECT message_id FROM messages WHERE session_id=? ORDER BY sequence", { bind(record.id,$0,1) }) { text($0,0) }
                    guard ids.first == record.messages.first?.id, ids.last == record.messages.last?.id else { throw error("migration order verification") }
                }
                if !fm.fileExists(atPath:backup.path){try fm.moveItem(at:file,to:backup)}
            } catch {
                if let data = try? Data(contentsOf:file), let record = try? Self.decoder.decode(SessionRecord.self,from:data) { try? delete(record.id) }
                // Keep the source JSON untouched. A later launch retries this session.
            }
        }
    }

    private func upsertRows(_ messages: [ChatMessage], sessionId: String) throws {
        try createSession(id: sessionId, agentId: "main_agent", agentName: "Main 智能编排")
        for message in messages {
            let payload = try Self.encoder.encode(PersistedMessage(message))
            if let n = try sequence(sessionId, message.id) {
                try run("UPDATE messages SET role=?,payload=? WHERE session_id=? AND sequence=?") { s in bind(message.role.rawValue,s,1); bind(payload,s,2); bind(sessionId,s,3); sqlite3_bind_int64(s,4,n) }
            } else {
                let n = try int64("SELECT next_sequence FROM sessions WHERE id=?", { bind(sessionId,$0,1) })
                try run("INSERT INTO messages(session_id,sequence,message_id,role,payload) VALUES(?,?,?,?,?)") { s in bind(sessionId,s,1); sqlite3_bind_int64(s,2,n); bind(message.id,s,3); bind(message.role.rawValue,s,4); bind(payload,s,5) }
                try run("UPDATE sessions SET next_sequence=?,message_count=message_count+1 WHERE id=?") { s in sqlite3_bind_int64(s,1,n+1); bind(sessionId,s,2) }
            }
        }
        let firstUser = try query("SELECT payload FROM messages WHERE session_id=? AND role=? ORDER BY sequence LIMIT 1", { s in bind(sessionId,s,1); bind(MessageRole.user.rawValue,s,2) }) { s in decode(s,0,sessionId).content }.first
        try run("UPDATE sessions SET title=COALESCE(?,title),updated_at=? WHERE id=?") { s in
            if let t = firstUser.map({String($0.trimmingCharacters(in:.whitespacesAndNewlines).prefix(20))}), !t.isEmpty { bind(t,s,1) } else { sqlite3_bind_null(s,1) }
            sqlite3_bind_double(s,2,Date().timeIntervalSince1970); bind(sessionId,s,3)
        }
    }

    private func refreshCount(_ id:String)throws{let c=try int64("SELECT COUNT(*) FROM messages WHERE session_id=?",{bind(id,$0,1)});let n=try int64("SELECT COALESCE(MAX(sequence),-1)+1 FROM messages WHERE session_id=?",{bind(id,$0,1)});try run("UPDATE sessions SET message_count=?,next_sequence=?,updated_at=? WHERE id=?"){s in sqlite3_bind_int64(s,1,c);sqlite3_bind_int64(s,2,n);sqlite3_bind_double(s,3,Date().timeIntervalSince1970);bind(id,s,4)}}
    private func sequence(_ sid:String,_ mid:String)throws->Int64?{try query("SELECT sequence FROM messages WHERE session_id=? AND message_id=? LIMIT 1",{s in bind(sid,s,1);bind(mid,s,2)}){sqlite3_column_int64($0,0)}.first}
    private func exists(_ sid:String,_ c:String,_ n:Int64)throws->Bool{try int64("SELECT EXISTS(SELECT 1 FROM messages WHERE session_id=? AND \(c) LIMIT 1)",{s in bind(sid,s,1);sqlite3_bind_int64(s,2,n)}) != 0}
    private func decode(_ s:OpaquePointer?,_ c:Int32,_ sid:String)->ChatMessage{let n=Int(sqlite3_column_bytes(s,c));let d=Data(bytes:sqlite3_column_blob(s,c),count:n);return (try? Self.decoder.decode(PersistedMessage.self,from:d).toChatMessage(sessionId:sid)) ?? ChatMessage(sessionId:sid,role:.assistant,content:"历史消息读取失败")}
    private func withConnectionLock<T>(_ body: () throws -> T) rethrows -> T {
        connectionLock.lock()
        defer { connectionLock.unlock() }
        return try body()
    }
    private func transaction(_ body:()throws->Void)throws {
        try withConnectionLock {
            try exec("BEGIN IMMEDIATE")
            do {
                try body()
                try exec("COMMIT")
            } catch {
                try? exec("ROLLBACK")
                throw error
            }
        }
    }
    private func exec(_ sql:String)throws {
        try withConnectionLock {
            guard sqlite3_exec(db,sql,nil,nil,nil)==SQLITE_OK else{throw error(sql)}
        }
    }
    private func run(_ sql:String,_ binds:(OpaquePointer?)->Void={_ in})throws {
        try withConnectionLock {
            var s:OpaquePointer?
            guard sqlite3_prepare_v2(db,sql,-1,&s,nil)==SQLITE_OK else{throw error(sql)}
            defer{sqlite3_finalize(s)}
            binds(s)
            guard sqlite3_step(s)==SQLITE_DONE else{throw error(sql)}
        }
    }
    private func query<T>(_ sql:String,_ binds:(OpaquePointer?)->Void={_ in},_ map:(OpaquePointer?)->T)throws->[T] {
        try withConnectionLock {
            var s:OpaquePointer?
            guard sqlite3_prepare_v2(db,sql,-1,&s,nil)==SQLITE_OK else{throw error(sql)}
            defer{sqlite3_finalize(s)}
            binds(s)
            var r:[T]=[]
            while sqlite3_step(s)==SQLITE_ROW{r.append(map(s))}
            return r
        }
    }
    private func int64(_ sql:String,_ binds:(OpaquePointer?)->Void={_ in})throws->Int64{try query(sql,binds){sqlite3_column_int64($0,0)}.first ?? 0}
    private func bind(_ x:String,_ s:OpaquePointer?,_ i:Int32){sqlite3_bind_text(s,i,x,-1,Self.transient)}
    private func bind(_ x:Data,_ s:OpaquePointer?,_ i:Int32){_ = x.withUnsafeBytes{sqlite3_bind_blob(s,i,$0.baseAddress,Int32($0.count),Self.transient)}}
    private func text(_ s:OpaquePointer?,_ i:Int32)->String{guard let p=sqlite3_column_text(s,i)else{return ""};return String(cString:p)}
    private func optionalDate(_ s: OpaquePointer?, _ i: Int32) -> Date? {
        guard sqlite3_column_type(s, i) != SQLITE_NULL else { return nil }
        return Date(timeIntervalSince1970: sqlite3_column_double(s, i))
    }
    private func error(_ context:String)->NSError{NSError(domain:"ChatHistoryStore",code:Int(sqlite3_errcode(db)),userInfo:[NSLocalizedDescriptionKey:"\(context): \(db.flatMap(sqlite3_errmsg).map(String.init(cString:)) ?? "unknown")"])}
}
