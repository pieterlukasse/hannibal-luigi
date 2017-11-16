#!/usr/bin/env bash

if [ $# -ne 1 ]; then
    echo "Usage: $0 <container_tag> <ES_URL>"
    exit 1
fi

DATE=$(date +"%m%d-%H%M")
CONTAINER_TAG=$1
ESMACHINE=${2:-elasticsearch}
echo Will point to ES: $ESMACHINE:9200


gcloud beta compute --project "open-targets-eu-dev" instances create "hannibal-$1-$DATE" \
 --zone "europe-west1-d" \
 --subnet "default" \
--machine-type "custom-40-266240" \
 --no-restart-on-failure \
 --maintenance-policy "TERMINATE" \
 --scopes default,storage-rw \
 --min-cpu-platform "Automatic" \
 --image-project "debian-cloud" \
 --image-family debian-9 \
 --boot-disk-size "250" \
 --boot-disk-type "pd-ssd" \
 --boot-disk-device-name "hannibal-$CONTAINER_TAG-$DATE" \
 --metadata-from-file startup-script=hannibal-debian.sh \
 --metadata "container-tag=$CONTAINER_TAG","es-url=$ESMACHINE" \
 --labels app=hannibal \
 --preemptible

#  --machine-type "n1-standard-1" \





