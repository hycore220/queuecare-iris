Class QueueCare.Production Extends Ens.Production
{
XData ProductionDefinition
{
<Production Name="QueueCare.Production" LogGeneralTraceEvents="true">
  <ActorPoolSize>2</ActorPoolSize>
  <Item Name="QueueCare.Service.Events" ClassName="QueueCare.Service.Events" PoolSize="1" Enabled="true" Foreground="false" />
  <Item Name="QueueCare.Process.Recovery" ClassName="QueueCare.Process.Recovery" PoolSize="1" Enabled="true" Foreground="false" />
  <Item Name="QueueCare.Operation.Recovery" ClassName="QueueCare.Operation.Recovery" PoolSize="1" Enabled="true" Foreground="false">
    <Setting Target="Host" Name="FailureTimeout">180</Setting>
  </Item>
</Production>
}
}
