/// Append-only through the application API; not a tamper-proof administrator log.
Class QueueCare.Data.Journal Extends %Persistent
{
Property KeyHash As %String(MAXLEN = 64) [ Required ];
Property EventType As %String(MAXLEN = 64);
Property Actor As %String(MAXLEN = 128);
Property DetailJSON As %String(MAXLEN = 32768);
Property CreatedAt As %TimeStamp;
Index EventKey On KeyHash;
}
