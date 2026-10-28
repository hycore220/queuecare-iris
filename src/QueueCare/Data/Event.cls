/// Immutable input/proposal/decision snapshots plus an explicit approval state.
Class QueueCare.Data.Event Extends %Persistent
{
Property KeyHash As %String(MAXLEN = 64) [ Required ];
Property Source As %String(MAXLEN = 256);
Property EventID As %String(MAXLEN = 128);
Property EventHash As %String(MAXLEN = 64);
Property EventJSON As %String(MAXLEN = 32768);
Property OrderJSON As %String(MAXLEN = 32768);
Property AliasJSON As %String(MAXLEN = 32768);
Property ProposalJSON As %String(MAXLEN = 16384);
Property DecisionJSON As %String(MAXLEN = 32768);
Property State As %String(MAXLEN = 64);
Property Mode As %String(MAXLEN = 32);
Property AICallCompleted As %Boolean [ InitialExpression = 0 ];
Property AIMetricsJSON As %String(MAXLEN = 16384);
Property CreatedAt As %TimeStamp;
Property UpdatedAt As %TimeStamp;
Index EventKey On KeyHash [ IdKey ];
}
