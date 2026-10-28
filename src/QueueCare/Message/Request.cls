Class QueueCare.Message.Request Extends Ens.Request
{
Property Command As %String [ InitialExpression = "submit" ];
Property EventJSON As %String(MAXLEN = 32768);
Property Mode As %String [ InitialExpression = "live" ];
Property ProposalJSON As %String(MAXLEN = 16384);
Property Source As %String(MAXLEN = 256);
Property EventID As %String(MAXLEN = 128);
Property Approve As %Boolean [ InitialExpression = 0 ];
Property Reviewer As %String(MAXLEN = 128);
}
