#!/usr/bin/env bash

docker pull amazon/dynamodb-local
docker run -d -p 8000:8000 amazon/dynamodb-local
aws dynamodb create-table \
    --table-name medicaid-details-unit-test \
    --attribute-definitions \
        AttributeName=email,AttributeType=S \
        AttributeName=application_uuid,AttributeType=S \
    --key-schema AttributeName=email,KeyType=HASH AttributeName=application_uuid,KeyType=RANGE \
    --provisioned-throughput ReadCapacityUnits=1,WriteCapacityUnits=1 \
    --region us-east-1 \
    --endpoint-url http://localhost:8000


