Include (%occStatus, Ensemble)
Class QueueCare.Setup Extends %RegisteredObject
{
ClassMethod LoadTrustedOrder(orderJSON As %String) As %Status
{
    Set order=##class(%DynamicObject).%FromJSON(orderJSON)
    Set key=##class(QueueCare.Bridge).TextHash(order."order_id")
    Set row=##class(QueueCare.Data.OrderRecord).%OpenId(key)
    If '$IsObject(row) Set row=##class(QueueCare.Data.OrderRecord).%New()
    Set row.KeyHash=key, row.OrderID=order."order_id", row.JSON=orderJSON
    Quit row.%Save()
}

ClassMethod SeedDemo() As %Status
{
    Set order={"order_id":"ORD-42","sku":"SKU-100","quantity":2}
    $$$ThrowOnError(..LoadTrustedOrder(order.%ToJSON()))
    Set aliases={"legacy-blue":["SKU-100"],"blue":["SKU-100","SKU-200"]}
    Set ^QueueCareConfig("aliases")=aliases.%ToJSON()
    Quit $$$OK
}

ClassMethod Start() As %Status
{
    Set sc=##class(Ens.Director).GetProductionStatus(.production,.state)
    If $$$ISERR(sc) Quit sc
    If state=$$$eProductionStateRunning {
        If production="QueueCare.Production" Return $$$OK
        Return $$$ERROR($$$GeneralError,"Another production is running in this namespace.")
    }
    Quit ##class(Ens.Director).StartProduction("QueueCare.Production")
}
}
