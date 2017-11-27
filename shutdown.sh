#!/bin/bash

echo "stopping LUIGI service"
systemctl stop luigi.service

echo "stopping mrTarget docker containers"
docker stop $(docker ps -q --filter name=mrT*)

echo "flushing ES"
curl -XPOST 'localhost:9200/_flush/synced?pretty'

echo "Done flushing, shutting down."