Include %occStatus
Class QueueCare.API Extends %RegisteredObject
{
ClassMethod Submit(eventJSON As %String, mode As %String = "live", proposalJSON As %String = "") As %String
{
    Set request=##class(QueueCare.Message.Request).%New()
    Set request.EventJSON=eventJSON, request.Mode=mode, request.ProposalJSON=proposalJSON
    Quit ..Send(request)
}

ClassMethod Approve(source As %String, eventId As %String, approve As %Boolean = 1, reviewer As %String = "local-reviewer") As %String
{
    Set request=##class(QueueCare.Message.Request).%New()
    Set request.Command="approve", request.Source=source, request.EventID=eventId
    Set request.Approve=approve, request.Reviewer=reviewer
    Quit ..Send(request)
}

ClassMethod Send(request As QueueCare.Message.Request) As %String
{
    Try {
        $$$ThrowOnError(##class(Ens.Director).CreateBusinessService("QueueCare.Service.Events",.service))
        $$$ThrowOnError(service.ProcessInput(request,.response))
        Return response.JSON
    } Catch ex {
        Return ##class(QueueCare.Store).Error("production_error",ex.DisplayString())
    }
}
}
