#!/usr/bin/env bash

# ./launch-gce.sh -e conf -s /etc -l /usr/lib <container-tag> 

unset ESURL
unset PUBESURL
unset KEEPUP
unset CONTAINER_TAG

POSITIONAL=()
while [[ $# -gt 0 ]]
do
key="$1"

case $key in
    -e|--elasticsearch)
    ESURL="$2"
    shift # past argument
    shift # past value
    ;;
    -p|--publications)
    PUBESURL="$2"
    shift # past argument
    shift # past value
    ;;
    --keepup)
    KEEPUP=YES
    shift # past argument
    ;;
    *)    # unknown option
    POSITIONAL+=("$1") # save it in an array for later
    shift # past argument
    ;;
esac
done
set -- "${POSITIONAL[@]}" # restore positional parameters

if [ -n "$KEEPUP" ]; then
    echo "WARNING - The machine will *not* be deleted after completion"
fi

if [ -z "$ESURL" ]; then
    echo "INFO - using internal elasticsearch with docker container"
    ESURL=http://elasticsearch:9200
fi

if [ -z "$PUBESURL" ]; then
    echo "WARNING - using default publication elasticsearch ip"
    PUBESURL=http://35.189.243.117:39200
fi

DATE=$(date +"%m%d-%H%M")

if [ $# -ne 1 ]; then
    echo "ERROR - container tag (ie. a github branch or github tag) must be specified"
    echo "Usage: $0 <container_tag> -p/--publication <ESPUBURL> -e/--elasticsearch <ES_URL>"
    exit 1
else
    CONTAINER_TAG="$1"
    echo "INFO - Creating a machine on gcloud named:           hannibal-$1-$DATE"
    echo "ES URL          = "${ESURL}""
    echo "PUB ES URL      = "${PUBESURL}""
    echo "CONTAINER TAG   = "${CONTAINER_TAG}""
fi

# substitute 
#  --machine-type "n1-standard-1" \
# to debug with a smaller machine. 
#The memory and cpu allocation are automatically calculated

gcloud beta compute --project "open-targets-eu-dev" instances create "hannibal-$1-$DATE" \
 --zone "europe-west1-d" \
 --subnet "default" \
--machine-type "custom-40-266240" \
 --no-restart-on-failure \
 --maintenance-policy "TERMINATE" \
 --scopes default,storage-rw,compute-rw \
 --min-cpu-platform "Automatic" \
 --image-project "debian-cloud" \
 --image-family debian-9 \
 --boot-disk-size "250" \
 --boot-disk-type "pd-ssd" \
 --boot-disk-device-name "hannibal-$CONTAINER_TAG-$DATE" \
 --metadata-from-file startup-script=hannibal-debian.sh \
 --metadata "container-tag=$CONTAINER_TAG","es-url=$ESURL","pub-es-url=$PUBESURL" \
 --labels app=hannibal \
 --preemptible







