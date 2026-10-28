Include %occStatus

/// Durable demo workflow. The sink is local and never sends real orders.
Class QueueCare.Store Extends %RegisteredObject
{
ClassMethod Key(source As %String, eventId As %String) As %String
{
    Set value = [(source),(eventId)]
    Quit ##class(QueueCare.Bridge).TextHash(value.%ToJSON())
}

ClassMethod Error(code As %String, detail As %String = "") As %String
{
    Set result = {"ok":false,"error":(code),"detail":(detail)}
    Quit result.%ToJSON()
}

ClassMethod Log(key As %String, kind As %String, detail As %String = "{}", actor As %String = "workflow") As %Status
{
    Set row = ##class(QueueCare.Data.Journal).%New()
    Set row.KeyHash=key, row.EventType=kind, row.DetailJSON=detail, row.Actor=actor
    Set row.CreatedAt=$ZDATETIME($HOROLOG,3)
    Quit row.%Save()
}

ClassMethod Snapshot(row As QueueCare.Data.Event, duplicate As %Boolean = 0) As %String
{
    Set out = {"ok":true,"source":(row.Source),"event_id":(row.EventID),"state":(row.State),"mode":(row.Mode),"duplicate":(duplicate),"sink":"local-demo-only","external_delivery":false}
    If row.DecisionJSON'="" Set out.decision=##class(%DynamicObject).%FromJSON(row.DecisionJSON)
    Set out."original_sha256"=row.EventHash
    Set out."agent_call_completed"=row.AICallCompleted
    If row.AIMetricsJSON'="" Set out."agent_metrics"=##class(%DynamicObject).%FromJSON(row.AIMetricsJSON)
    Set out."created_at"=row.CreatedAt, out."updated_at"=row.UpdatedAt
    Quit out.%ToJSON()
}

ClassMethod Status(source As %String, eventId As %String) As %String
{
    Set row=##class(QueueCare.Data.Event).%OpenId(..Key(source,eventId))
    If '$IsObject(row) Return ..Error("not_found")
    Quit ..Snapshot(row)
}

ClassMethod Submit(eventJSON As %String, mode As %String = "live", proposalJSON As %String = "") As %String
{
    Set key="", locked=0
    Try {
        If (mode'="live")&&(mode'="replay") Return ..Error("invalid_mode")
        If (mode="live")&&(proposalJSON'="") Return ..Error("proposal_not_allowed_in_live_mode")
        Set ident=##class(%DynamicObject).%FromJSON(##class(QueueCare.Bridge).IdentityJson(eventJSON))
        Set key=..Key(ident.source,ident."event_id")
        Lock +^QueueCareLocks(key):5
        If '$Test Return ..Error("event_busy")
        Set locked=1
        Set row=##class(QueueCare.Data.Event).%OpenId(key)
        If $IsObject(row) {
            If row.EventHash'=ident."event_sha256" {
                $$$ThrowOnError(..Log(key,"identity_conflict"))
                Set out=..Error("identity_conflict","The same source/event ID has different content.")
            } Else {
                Set out=..Snapshot(row,1)
            }
        } Else {
            Set order=##class(QueueCare.Data.OrderRecord).%OpenId(##class(QueueCare.Bridge).TextHash(ident."order_id"))
            Set orderJSON="{}"
            If $IsObject(order) Set orderJSON=order.JSON
            Set aliasJSON=$Get(^QueueCareConfig("aliases"),"{}")
            Set row=##class(QueueCare.Data.Event).%New()
            Set row.KeyHash=key, row.Source=ident.source, row.EventID=ident."event_id"
            Set row.EventHash=ident."event_sha256", row.EventJSON=eventJSON
            Set row.OrderJSON=orderJSON, row.AliasJSON=aliasJSON, row.Mode=mode
            Set row.State="analyzing", row.CreatedAt=$ZDATETIME($HOROLOG,3), row.UpdatedAt=row.CreatedAt
            TStart
            $$$ThrowOnError(row.%Save())
            $$$ThrowOnError(..Log(key,"received"))
            TCommit
            Try {
                If '$IsObject(order) {
                    Set proposalJSON="{""proposed_action"":""manual_review""}"
                } ElseIf mode="live" {
                    If '##class(%Dictionary.CompiledClass).%ExistsId("QueueCare.Agent") {
                        Throw ##class(%Exception.General).%New("AI Hub agent is unavailable; no replay fallback is permitted.")
                    }
                    Set agent=$ClassMethod("QueueCare.Agent","%New")
                    $$$ThrowOnError(agent.%Init())
                    Set session=agent.CreateSession({"max_iterations":1,"temperature":0,"max_tokens":256})
                    Set response=agent.Chat(session,##class(QueueCare.Bridge).PromptJson(eventJSON,orderJSON,aliasJSON))
                    Set proposalJSON=response.Content
                    Set row.AICallCompleted=1
                    Set row.AIMetricsJSON=session.GetStats().%ToJSON()
                }
                Set decisionJSON=##class(QueueCare.Bridge).ValidateJson(eventJSON,orderJSON,proposalJSON,aliasJSON)
                Set decision=##class(%DynamicObject).%FromJSON(decisionJSON)
                Set row.ProposalJSON=proposalJSON, row.DecisionJSON=decisionJSON
                Set row.State="held"
                If decision.approved {
                    If decision.action="reject" Set row.State="rejected"
                    If (decision.action="normalize_sku")||(decision.action="retry_later") Set row.State="awaiting_approval"
                }
            } Catch inferenceError {
                Set row.State="held"
                Set failure={"approved":false,"action":"manual_review","reason_code":"inference_or_validation_error","reason":(inferenceError.DisplayString())}
                Set row.DecisionJSON=failure.%ToJSON()
            }
            Set row.UpdatedAt=$ZDATETIME($HOROLOG,3)
            TStart
            $$$ThrowOnError(row.%Save())
            $$$ThrowOnError(..Log(key,"decision_recorded",row.DecisionJSON))
            TCommit
            Set out=..Snapshot(row)
        }
    } Catch ex {
        If $TLevel TRollback
        Set out=..Error("workflow_error",ex.DisplayString())
    }
    If locked Lock -^QueueCareLocks(key)
    Quit out
}

ClassMethod Approve(source As %String, eventId As %String, approved As %Boolean, reviewer As %String) As %String
{
    Set key=..Key(source,eventId), locked=0
    Try {
        If (reviewer="")||($Length(reviewer)>128) Return ..Error("reviewer_required")
        Lock +^QueueCareLocks(key):5
        If '$Test Return ..Error("event_busy")
        Set locked=1
        Set row=##class(QueueCare.Data.Event).%OpenId(key)
        If '$IsObject(row) {
            Set out=..Error("not_found")
        } ElseIf (row.State="delivered_local")||(row.State="scheduled_local")||(row.State="denied") {
            Set out=..Snapshot(row,1)
        } ElseIf row.State'="awaiting_approval" {
            Set out=..Error("not_awaiting_approval",row.State)
        } Else {
            TStart
            If 'approved {
                Set row.State="denied"
                $$$ThrowOnError(..Log(key,"denied","{}",reviewer))
            } Else {
                Set event=##class(%DynamicObject).%FromJSON(row.EventJSON)
                Set order=##class(QueueCare.Data.OrderRecord).%OpenId(##class(QueueCare.Bridge).TextHash(event."order_id"))
                Set currentOrder="{}"
                If $IsObject(order) Set currentOrder=order.JSON
                Set currentAliases=$Get(^QueueCareConfig("aliases"),"{}")
                If (##class(QueueCare.Bridge).CanonicalHash(currentOrder)'=##class(QueueCare.Bridge).CanonicalHash(row.OrderJSON))||(##class(QueueCare.Bridge).CanonicalHash(currentAliases)'=##class(QueueCare.Bridge).CanonicalHash(row.AliasJSON)) {
                    Set row.State="held_stale_context"
                    $$$ThrowOnError(..Log(key,"approval_context_changed","{}",reviewer))
                } Else {
                    Set decisionJSON=##class(QueueCare.Bridge).ValidateJson(row.EventJSON,currentOrder,row.ProposalJSON,currentAliases)
                    Set decision=##class(%DynamicObject).%FromJSON(decisionJSON)
                    If 'decision.approved Throw ##class(%Exception.General).%New("Policy revalidation failed.")
                    Set delivery=##class(QueueCare.Data.Delivery).%New()
                    Set delivery.KeyHash=key, delivery.Action=decision.action
                    Set delivery.PayloadJSON=##class(QueueCare.Bridge).DeliveryJson(row.EventJSON,decisionJSON)
                    Set delivery.Reviewer=reviewer, delivery.CreatedAt=$ZDATETIME($HOROLOG,3)
                    Set row.State="delivered_local"
                    If decision.action="retry_later" {
                        Set row.State="scheduled_local"
                        Set delivery.RetryAfterSeconds=decision."retry_after_seconds"
                    }
                    $$$ThrowOnError(delivery.%Save())
                    $$$ThrowOnError(..Log(key,row.State,delivery.PayloadJSON,reviewer))
                }
            }
            Set row.UpdatedAt=$ZDATETIME($HOROLOG,3)
            $$$ThrowOnError(row.%Save())
            TCommit
            Set out=..Snapshot(row)
        }
    } Catch ex {
        If $TLevel TRollback
        Set out=..Error("approval_error",ex.DisplayString())
    }
    If locked Lock -^QueueCareLocks(key)
    Quit out
}
}
