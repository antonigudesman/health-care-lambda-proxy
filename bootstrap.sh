#!/usr/bin/env bash

sudo yum update -y
sudo amazon-linux-extras install docker
sudo service docker start
sudo docker pull amazon/dynamodb-local
sudo docker run -d -p 8000:8000 amazon/dynamodb-local
aws dynamodb create-table \
    --table-name medicaid-details \
    --attribute-definitions \
        AttributeName=email,AttributeType=S \
        AttributeName=application_uuid,AttributeType=S \
    --key-schema AttributeName=email,KeyType=HASH AttributeName=application_uuid,KeyType=RANGE \
    --provisioned-throughput ReadCapacityUnits=1,WriteCapacityUnits=1 \
    --endpoint-url http://localhost:8000
sudo yum install -y python3
sudo python3 -m pip install pipenv
cd /vagrant && export PIPENV_VENV_IN_PROJECT=1 && python3 -m pipenv install --skip-lock
