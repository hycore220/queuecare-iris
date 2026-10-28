Include %occStatus

/// Fixed synthetic scenarios for the optional local review console.
Class QueueCare.Demo Extends %RegisteredObject
{
ClassMethod Dispatch(requestJSON As %String) As %String
{
    Try {
        Set request=##class(%DynamicObject).%FromJSON(requestJSON)
        Set action=request.action
        If action="list" Return ..List()
        If action="create" {
            Set scenario=request.scenario, mode=request.mode
            If (scenario'="alias")&&(scenario'="unsafe")&&(scenario'="retry") Return ##class(QueueCare.Store).Error("invalid_scenario")
            If (mode'="live")&&(mode'="replay") Return ##class(QueueCare.Store).Error("invalid_mode")
            If (scenario="unsafe")&&(mode="live") Return ##class(QueueCare.Store).Error("unsafe_scenario_is_replay_only")
            $$$ThrowOnError(##class(QueueCare.Setup).Start())
            Set run=$Increment(^QueueCareDemoRun), id="demo-"_run
            Set event={"id":(id),"source":"web-demo","order_id":"ORD-42","sku":"legacy-blue","quantity":2,"status":"failed","retry_count":0}
            Set proposal={"proposed_action":"normalize_sku","patch":{"sku":"SKU-100"}}
            If scenario="unsafe" Set proposal.patch.quantity=200
            If scenario="retry" {
                Set event.sku="SKU-100"
                Set proposal={"proposed_action":"retry_later","retry_after_seconds":60}
            }
            Set proposalJSON=""
            If mode="replay" Set proposalJSON=proposal.%ToJSON()
            Set reply=##class(%DynamicObject).%FromJSON(##class(QueueCare.API).Submit(event.%ToJSON(),mode,proposalJSON))
            If 'reply.ok Return reply.%ToJSON()
            Set ^QueueCareDemoEvents(run)=id
            Return ..Detail(id)
        }
        Set source=request.%Get("source","web-demo")
        If (source'="web-demo")&&(source'="warehouse-file") Return ##class(QueueCare.Store).Error("invalid_source")
        Set id=request.id, key=##class(QueueCare.Store).Key(source,id)
        If '$Length(id) Return ##class(QueueCare.Store).Error("event_required")
        If action="detail" Return ..Detail(id,source)
        If action="approve" {
            Set reply=##class(%DynamicObject).%FromJSON(##class(QueueCare.API).Approve(source,id,1,"local-console-reviewer"))
            If 'reply.ok Return reply.%ToJSON()
            Return ..Detail(id,source)
        }
        If action="deny" {
            Set reply=##class(%DynamicObject).%FromJSON(##class(QueueCare.API).Approve(source,id,0,"local-console-reviewer"))
            If 'reply.ok Return reply.%ToJSON()
            Return ..Detail(id,source)
        }
        If action="duplicate" {
            Set row=##class(QueueCare.Data.Event).%OpenId(key)
            If '$IsObject(row) Return ##class(QueueCare.Store).Error("not_found")
            Set proposalJSON=""
            If row.Mode="replay" Set proposalJSON=row.ProposalJSON
            Set reply=##class(%DynamicObject).%FromJSON(##class(QueueCare.API).Submit(row.EventJSON,row.Mode,proposalJSON))
            If 'reply.ok Return reply.%ToJSON()
            Set out=##class(%DynamicObject).%FromJSON(..Detail(id,source)), out.duplicate=reply.duplicate
            Return out.%ToJSON()
        }
        Return ##class(QueueCare.Store).Error("invalid_action")
    } Catch ex {
        Return ##class(QueueCare.Store).Error("demo_error",ex.DisplayString())
    }
}

ClassMethod List() As %String
{
    Set out={"ok":true,"events":[],"sink":"local-demo-only"}
    Set statement=##class(%SQL.Statement).%New()
    $$$ThrowOnError(statement.%Prepare("SELECT TOP 50 KeyHash FROM QueueCare_Data.Event WHERE Source IN ('web-demo','warehouse-file') ORDER BY CreatedAt DESC, KeyHash"))
    Set result=statement.%Execute()
    While result.%Next() {
        Set row=##class(QueueCare.Data.Event).%OpenId(result.%Get("KeyHash"))
        If $IsObject(row) {
            Do out.events.%Push(##class(%DynamicObject).%FromJSON(##class(QueueCare.Store).Snapshot(row)))
        }
    }
    Quit out.%ToJSON()
}

ClassMethod Detail(id As %String, source As %String = "web-demo") As %String
{
    If (source'="web-demo")&&(source'="warehouse-file") Return ##class(QueueCare.Store).Error("invalid_source")
    Set key=##class(QueueCare.Store).Key(source,id)
    Set row=##class(QueueCare.Data.Event).%OpenId(key)
    If '$IsObject(row) Return ##class(QueueCare.Store).Error("not_found")
    Set out=##class(%DynamicObject).%FromJSON(##class(QueueCare.Store).Snapshot(row))
    Set out.input=##class(%DynamicObject).%FromJSON(row.EventJSON)
    Set out.order=##class(%DynamicObject).%FromJSON(row.OrderJSON)
    Set out.aliases=##class(%DynamicObject).%FromJSON(row.AliasJSON)
    Set out.proposal=row.ProposalJSON, out.journal=[]
    Set statement=##class(%SQL.Statement).%New()
    $$$ThrowOnError(statement.%Prepare("SELECT EventType, Actor, CreatedAt FROM QueueCare_Data.Journal WHERE KeyHash = ? ORDER BY ID"))
    Set result=statement.%Execute(key)
    While result.%Next() {
        Set item={"event":(result.%Get("EventType")),"actor":(result.%Get("Actor")),"at":(result.%Get("CreatedAt"))}
        Do out.journal.%Push(item)
    }
    Set delivery=##class(QueueCare.Data.Delivery).%OpenId(key)
    Set out."sink_record_count"=0
    If $IsObject(delivery) {
        Set out."sink_record_count"=1
        Set out.delivery=##class(%DynamicObject).%FromJSON(delivery.PayloadJSON)
        Set out."retry_after_seconds"=delivery.RetryAfterSeconds
    }
    Quit out.%ToJSON()
}
}
