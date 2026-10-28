Include %occStatus

Class QueueCare.Process.Recovery Extends Ens.BusinessProcess [ ClassType = persistent ]
{
Method OnRequest(pRequest As QueueCare.Message.Request, Output pResponse As QueueCare.Message.Response) As %Status
{
    // The destination is a queued BO with its own worker, not another pooled BP.
    Quit ..SendRequestSync("QueueCare.Operation.Recovery", pRequest, .pResponse, 170)
}
}
