/// Local demonstration sink. No network delivery and no retry worker are implemented.
Class QueueCare.Data.Delivery Extends %Persistent
{
Property KeyHash As %String(MAXLEN = 64) [ Required ];
Property Action As %String(MAXLEN = 64);
Property PayloadJSON As %String(MAXLEN = 32768);
Property Reviewer As %String(MAXLEN = 128);
Property RetryAfterSeconds As %Integer;
Property CreatedAt As %TimeStamp;
Index DeliveryKey On KeyHash [ IdKey ];
}
