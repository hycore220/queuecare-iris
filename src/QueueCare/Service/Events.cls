Include %occStatus

Class QueueCare.Service.Events Extends Ens.BusinessService
{
Parameter ADAPTER = "";

Method OnProcessInput(pInput As QueueCare.Message.Request, Output pOutput As QueueCare.Message.Response) As %Status
{
    Quit ..SendRequestSync("QueueCare.Process.Recovery", pInput, .pOutput, 180)
}
}
