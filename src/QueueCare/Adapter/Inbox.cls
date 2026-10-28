Include (%occStatus, Ensemble)

/// Custom transport: atomically claims a completed JSON event and keeps a receipt.
Class QueueCare.Adapter.Inbox Extends Ens.InboundAdapter
{
Property InboxRoot As %String [ InitialExpression = "/home/irisowner/queuecare/inbox" ];
Parameter SETTINGS = "InboxRoot:Connection";

Method OnTask() As %Status
{
    Set token="", ..BusinessHost.%WaitForNextCallInterval=1
    Try {
        Set token=##class(QueueCare.Inbox).Claim(..InboxRoot)
        If token="" Return $$$OK
        Set request=##class(QueueCare.Message.Request).%New()
        Set request.EventJSON=##class(QueueCare.Inbox).Read(..InboxRoot,token)
        Set request.Mode="live"
        $$$ThrowOnError(..BusinessHost.ProcessInput(request,.response))
        Set result=##class(%DynamicObject).%FromJSON(response.JSON)
        Set receipt=##class(QueueCare.Inbox).Finish(..InboxRoot,token,response.JSON,'result.ok)
    } Catch ex {
        If token'="" {
            Set error=##class(QueueCare.Store).Error("file_ingestion_error",ex.DisplayString())
            Try {
                Set receipt=##class(QueueCare.Inbox).Finish(..InboxRoot,token,error,1)
            } Catch receiptError {
                // Leave the claimed file for manual recovery if storage failed.
                Return receiptError.AsStatus()
            }
        } Else {
            Return ex.AsStatus()
        }
    }
    Quit $$$OK
}
}
