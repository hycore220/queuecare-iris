Include %occStatus

Class QueueCare.Operation.Recovery Extends Ens.BusinessOperation
{
Parameter ADAPTER = "";
Parameter INVOCATION = "Queue";

Method Handle(pRequest As QueueCare.Message.Request, Output pResponse As QueueCare.Message.Response) As %Status
{
    Set pResponse = ##class(QueueCare.Message.Response).%New()
    If pRequest.Command = "submit" {
        Set pResponse.JSON = ##class(QueueCare.Store).Submit(pRequest.EventJSON, pRequest.Mode, pRequest.ProposalJSON)
    } ElseIf pRequest.Command = "approve" {
        Set pResponse.JSON = ##class(QueueCare.Store).Approve(pRequest.Source, pRequest.EventID, pRequest.Approve, pRequest.Reviewer)
    } Else {
        Set pResponse.JSON = {"ok":false,"error":"unknown_command"}.%ToJSON()
    }
    Quit $$$OK
}

XData MessageMap
{
<MapItems>
  <MapItem MessageType="QueueCare.Message.Request"><Method>Handle</Method></MapItem>
</MapItems>
}
}
