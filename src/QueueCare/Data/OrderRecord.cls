/// Authoritative demo orders. Only administrator setup methods populate this table.
Class QueueCare.Data.OrderRecord Extends %Persistent
{
Property KeyHash As %String(MAXLEN = 64) [ Required ];
Property OrderID As %String(MAXLEN = 128);
Property JSON As %String(MAXLEN = 32768);
Index OrderKey On KeyHash [ IdKey ];
}
