#!/usr/bin/env bash

docker pull amazon/dynamodb-local
docker run -d -p 8000:8000 amazon/dynamodb-local
#docker run -d --network host --name dyanolocal amazon/dynamodb-local
sleep 5
aws dynamodb create-table \
    --table-name medicaid-details \
    --attribute-definitions \
        AttributeName=email,AttributeType=S \
        AttributeName=application_uuid,AttributeType=S \
    --key-schema AttributeName=email,KeyType=HASH AttributeName=application_uuid,KeyType=RANGE \
    --provisioned-throughput ReadCapacityUnits=1,WriteCapacityUnits=1 \
    --endpoint-url http://localhost:8000
