Include %occStatus

Class QueueCare.Tests Extends %RegisteredObject
{
ClassMethod Assert(condition As %Boolean, label As %String, checks As %DynamicArray)
{
    Set item={"name":(label),"passed":(condition)}
    Do checks.%Push(item)
    If 'condition Throw ##class(%Exception.General).%New("Assertion failed: "_label)
}

ClassMethod Run() As %String
{
    Set checks=[], out={"evidence_kind":"IRIS-154-production-integration-replay","external_delivery":false}
    Set out.version=$ZVERSION
    Try {
        $$$ThrowOnError(##class(QueueCare.Setup).SeedDemo())
        $$$ThrowOnError(##class(QueueCare.Setup).Start())
        Set run=$Increment(^QueueCareTestRun), prefix="test-"_run_"-"
        Set event={"id":(prefix_"alias"),"source":"test","order_id":"ORD-42","sku":"legacy-blue","quantity":2,"status":"failed","retry_count":0}
        Set proposal={"proposed_action":"normalize_sku","patch":{"sku":"SKU-100"}}
        Set reply=##class(%DynamicObject).%FromJSON(##class(QueueCare.API).Submit(event.%ToJSON(),"replay",proposal.%ToJSON()))
        Do ..Assert(reply.ok,"service-process-operation round trip",checks)
        Do ..Assert(reply.state="awaiting_approval","validated proposal waits for approval",checks)
        Set key=##class(QueueCare.Store).Key("test",event.id)
        Do ..Assert('##class(QueueCare.Data.Delivery).%ExistsId(key),"no sink write before approval",checks)
        Set repeated=##class(%DynamicObject).%FromJSON(##class(QueueCare.API).Submit(event.%ToJSON(),"replay",proposal.%ToJSON()))
        Do ..Assert(repeated.duplicate=1,"duplicate input returns existing record",checks)
        Set event.quantity=999
        Set conflict=##class(%DynamicObject).%FromJSON(##class(QueueCare.API).Submit(event.%ToJSON(),"replay",proposal.%ToJSON()))
        Do ..Assert(conflict.error="identity_conflict","same ID different content rejected",checks)
        Set event.quantity=2
        Set approved=##class(%DynamicObject).%FromJSON(##class(QueueCare.API).Approve("test",event.id,1,"integration-test"))
        Do ..Assert(approved.state="delivered_local","approval writes local demo sink",checks)
        Set sink=##class(QueueCare.Data.Delivery).%OpenId(key)
        Set payload=##class(%DynamicObject).%FromJSON(sink.PayloadJSON)
        Do ..Assert((payload.sku="SKU-100")&&(payload.quantity=2)&&(payload."order_id"="ORD-42"),"only SKU changed",checks)
        Set again=##class(%DynamicObject).%FromJSON(##class(QueueCare.API).Approve("test",event.id,1,"integration-test"))
        Do ..Assert((again.duplicate=1)&&(again.state="delivered_local"),"repeat approval is idempotent",checks)

        Set event.id=prefix_"injection"
        Set malicious={"proposed_action":"normalize_sku","patch":{"sku":"SKU-100","quantity":200}}
        Set held=##class(%DynamicObject).%FromJSON(##class(QueueCare.API).Submit(event.%ToJSON(),"replay",malicious.%ToJSON()))
        Do ..Assert(held.state="held","illegal quantity patch held",checks)
        Set rejected=##class(%DynamicObject).%FromJSON(##class(QueueCare.API).Approve("test",event.id,1,"integration-test"))
        Do ..Assert(rejected.error="not_awaiting_approval","held proposal cannot be approved",checks)

        Set event.id=prefix_"stale"
        Set pending=##class(%DynamicObject).%FromJSON(##class(QueueCare.API).Submit(event.%ToJSON(),"replay",proposal.%ToJSON()))
        Set changed={"order_id":"ORD-42","sku":"SKU-100","quantity":3}
        $$$ThrowOnError(##class(QueueCare.Setup).LoadTrustedOrder(changed.%ToJSON()))
        Set stale=##class(%DynamicObject).%FromJSON(##class(QueueCare.API).Approve("test",event.id,1,"integration-test"))
        Do ..Assert(stale.state="held_stale_context","changed authoritative order blocks approval",checks)
        Do ..Assert('##class(QueueCare.Data.Delivery).%ExistsId(##class(QueueCare.Store).Key("test",event.id)),"stale context never reaches sink",checks)
        $$$ThrowOnError(##class(QueueCare.Setup).SeedDemo())

        Set event.id=prefix_"denied"
        Set pending=##class(%DynamicObject).%FromJSON(##class(QueueCare.API).Submit(event.%ToJSON(),"replay",proposal.%ToJSON()))
        Set denied=##class(%DynamicObject).%FromJSON(##class(QueueCare.API).Approve("test",event.id,0,"integration-test"))
        Do ..Assert(denied.state="denied","reviewer may deny valid proposal",checks)
        Do ..Assert('##class(QueueCare.Data.Delivery).%ExistsId(##class(QueueCare.Store).Key("test",event.id)),"denial creates no delivery",checks)

        Set event.id=prefix_"retry", event.sku="SKU-100"
        Set retry={"proposed_action":"retry_later","retry_after_seconds":60}
        Set pending=##class(%DynamicObject).%FromJSON(##class(QueueCare.API).Submit(event.%ToJSON(),"replay",retry.%ToJSON()))
        Set scheduled=##class(%DynamicObject).%FromJSON(##class(QueueCare.API).Approve("test",event.id,1,"integration-test"))
        Do ..Assert(scheduled.state="scheduled_local","retry produces a local schedule record",checks)
        Set sink=##class(QueueCare.Data.Delivery).%OpenId(##class(QueueCare.Store).Key("test",event.id))
        Do ..Assert(sink.RetryAfterSeconds=60,"retry interval preserved",checks)
        Set out.passed=1
    } Catch ex {
        Set out.passed=0, out.error=ex.DisplayString()
    }
    Set out.checks=checks
    Set out."checks_run"=checks.%Size()
    Quit out.%ToJSON()
}

ClassMethod WriteReport() As %Status
{
    Set json=..Run()
    Set file=##class(%Stream.FileCharacter).%New()
    Set file.Filename="/home/irisowner/queuecare/reports/iris-integration.json"
    $$$ThrowOnError(file.Write(json))
    $$$ThrowOnError(file.%Save())
    Write json,!
    Quit $$$OK
}
}
