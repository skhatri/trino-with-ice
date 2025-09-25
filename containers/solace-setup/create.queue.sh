#!/bin/bash

host=solace
port="8080"

create_queue(){
  local queueName=$1
  echo "Creating new queue in Solace"
  curl "http://$host:$port/SEMP/v2/config/msgVpns/default/queues" \
    -X POST \
    -u admin:password \
    -H "Content-type:application/json" \
    -d '{ "queueName":"'$queueName'","accessType":"exclusive","maxMsgSpoolUsage":200,"permission":"consume","ingressEnabled":true,"egressEnabled":true }'

  echo "Creating JNDI queue object"
  curl "http://$host:$port/SEMP/v2/config/msgVpns/default/jndiQueues" \
    -X POST \
    -u admin:password \
    -H "Content-type:application/json" \
    -d '{ "msgVpnName":"default","physicalName":"'$queueName'","queueName":"/JNDI/Q/'$queueName'" }'
}

create_topic_queue(){
  local queueName=$1
  local topicName=$2
  echo "Creating new topic in Solace"
  curl http://$host:$port/SEMP/v2/config/msgVpns/default/topicEndpoints \
    -X POST \
    -u admin:password \
    -H "Content-type:application/json" \
    -d "{ \"topicEndpointName\":\"$topicName\",\"accessType\":\"exclusive\",\"maxSpoolUsage\":200,\"permission\":\"consume\",\"ingressEnabled\":true,\"egressEnabled\":true }"

  echo "Creating JNDI queue object"
  curl http://$host:$port/SEMP/v2/config/msgVpns/default/jndiTopics \
    -X POST \
    -u admin:password \
    -H "Content-type:application/json" \
    -d '{ "msgVpnName":"default","physicalName":"'$topicName'","topicName":"/JNDI/T/'$topicName'" }'

  echo "Creating subscription between queue and topic"
  curl http://$host:$port/SEMP/v2/config/msgVpns/default/queues/$queueName/subscriptions \
    -X POST \
    -u admin:password \
    -H "Content-type:application/json" \
    -d "{ \"msgVpnName\":\"default\",\"queueName\":\"$queueName\",\"subscriptionTopic\":\"$topicName\" }"


}
#Swagger doc: https://docs.solace.com/API-Developer-Online-Ref-Documentation/swagger-ui/software-broker/config/index.html
while IFS= read -r line; do
  if [ -z "$line" ] || [[ "$line" == \#* ]]; then
    continue
  fi;
  IFS='=' read -r queue topics <<< "$line"
  create_queue $queue
  IFS=',' read -ra values <<< "$topics"
  for topic in "${values[@]}"; do
    echo "create topic $topic"
    create_topic_queue $queue $topic
  done
done < "/tmp/scripts/queue.properties"

