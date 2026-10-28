Include %occStatus

Class QueueCare.Service.Inbox Extends Ens.BusinessService
{
Parameter ADAPTER = "QueueCare.Adapter.Inbox";

Method OnProcessInput(pInput As QueueCare.Message.Request, Output pOutput As QueueCare.Message.Response) As %Status
{
    Try {
        Set identity=##class(%DynamicObject).%FromJSON(##class(QueueCare.Bridge).IdentityJson(pInput.EventJSON))
        If identity.source'="warehouse-file" Throw ##class(%Exception.General).%New("File events must use source warehouse-file.")
        // The transport accepts events only: no replay proposal or approval command.
        Set pInput.Command="submit", pInput.Mode="live", pInput.ProposalJSON=""
        Return ..SendRequestSync("QueueCare.Process.Recovery",pInput,.pOutput,170)
    } Catch ex {
        Set pOutput=##class(QueueCare.Message.Response).%New()
        Set pOutput.JSON=##class(QueueCare.Store).Error("file_event_invalid",ex.DisplayString())
    }
    Quit $$$OK
}
}
