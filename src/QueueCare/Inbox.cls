/// Filesystem transport helpers. No model or workflow is invoked here.
Class QueueCare.Inbox Extends %RegisteredObject
{
Parameter ROOT = "/home/irisowner/queuecare/inbox";

ClassMethod Claim(root As %String) As %String [ Language = python ]
{
    from queuecare.inbox import claim
    return claim(root)
}

ClassMethod Read(root As %String, token As %String) As %String [ Language = python ]
{
    from queuecare.inbox import read_event
    return read_event(root, token)
}

ClassMethod Finish(root As %String, token As %String, resultJSON As %String, rejected As %Boolean = 0) As %String [ Language = python ]
{
    from queuecare.inbox import finish
    return finish(root, token, resultJSON, bool(rejected))
}

ClassMethod Publish(eventJSON As %String) As %String
{
    Quit ..PublishAt(..#ROOT,eventJSON)
}

ClassMethod PublishAt(root As %String, eventJSON As %String) As %String [ Language = python ]
{
    from queuecare.inbox import publish
    return publish(root, eventJSON)
}

ClassMethod Sample() As %String
{
    Set id="file-"_$Increment(^QueueCareFileRun)
    Set event={"id":(id),"source":"warehouse-file","order_id":"ORD-42","sku":"legacy-blue","quantity":2,"status":"failed","retry_count":0}
    Set filename=..Publish(event.%ToJSON())
    Quit {"ok":true,"queued":true,"event_id":(id),"source":"warehouse-file","filename":(filename)}.%ToJSON()
}
}
