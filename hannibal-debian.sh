#!/bin/bash

apt-get update && DEBIAN_FRONTEND=noninteractive \
    apt-get \
    -o Dpkg::Options::="--force-confnew" \
    --force-yes \
    -fuy \
    dist-upgrade && \
    DEBIAN_FRONTEND=noninteractive \
    apt-get \
    -o Dpkg::Options::="--force-confnew" \
    --force-yes \
    -fuy \
    -t stretch-backports install net-tools \
                                    wget less tmux htop jq httpie\
                                    uuid-runtime \
                                    python-pip \
                                    python-dev \
                                    libyaml-dev \
                                    apt-transport-https \
                                    ca-certificates \
                                    curl \
                                    gnupg2 \
                                    software-properties-common

curl -fsSL https://download.docker.com/linux/$(. /etc/os-release; echo "$ID")/gpg | sudo apt-key add -

add-apt-repository \
   "deb [arch=amd64] https://download.docker.com/linux/$(. /etc/os-release; echo "$ID") \
   $(lsb_release -cs) \
   stable"

apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y docker-ce

systemctl enable docker

cat <<EOF >> ~/.bashrc
# Sensible Bash - An attempt at saner Bash defaults
# Repository: https://github.com/mrzool/bash-sensible

## GENERAL OPTIONS ##
set -o noclobber
shopt -s checkwinsize
PROMPT_DIRTRIM=2
bind Space:magic-space
shopt -s globstar 2> /dev/null
shopt -s nocaseglob;

## SMARTER TAB-COMPLETION (Readline bindings) ##
bind "set completion-ignore-case on"
bind "set completion-map-case on"
bind "set show-all-if-ambiguous on"
bind "set mark-symlinked-directories on"

## SANE HISTORY DEFAULTS ##
shopt -s histappend
shopt -s cmdhist
PROMPT_COMMAND='history -a'
HISTSIZE=500000
HISTFILESIZE=100000
HISTCONTROL="erasedups:ignoreboth"
export HISTIGNORE="&:[ ]*:exit:ls:bg:fg:history:clear"
HISTTIMEFORMAT='%F %T '
# Enable incremental history search with up/down arrows (also Readline goodness)
bind '"\e[A": history-search-backward'
bind '"\e[B": history-search-forward'
bind '"\e[C": forward-char'
bind '"\e[D": backward-char'

## BETTER DIRECTORY NAVIGATION ##
shopt -s autocd 2> /dev/null
shopt -s dirspell 2> /dev/null
shopt -s cdspell 2> /dev/null
CDPATH="."

### Variables I need for ES and Luigi ###
## Compute half memtotal gigs 
# cap ES heap at 26 to safely remain under zero-base compressed oops limit
# see: https://www.elastic.co/guide/en/elasticsearch/reference/current/heap-size.html
ES_MEM=\$(awk '/MemTotal/ {half=\$2/1024/2; if (half > 52*1024) printf 52*1024; else printf "%d", half}' /proc/meminfo)
ES_HEAP=\$((\$ES_MEM/2))

## Cap CPUs for ES to 8
ES_CPU=\$(awk '/cpu cores/ {if (\$NF/2 < 8) print \$NF/2; else print 8}' /proc/cpuinfo)

INSTANCE_NAME=\$(http --ignore-stdin --check-status 'http://metadata.google.internal/computeMetadata/v1/instance/name'  "Metadata-Flavor:Google" -p b --pretty none)
CONTAINER_TAG=\$(http --ignore-stdin --check-status 'http://metadata.google.internal/computeMetadata/v1/instance/attributes/container-tag'  "Metadata-Flavor:Google" -p b --pretty none)

LUIGI_CONFIG_PATH=/hannibal/luigi.cfg
EOF

## install stackdriver logging agent 
# as explained in https://cloud.google.com/logging/docs/agent/installation
curl -sSO https://dl.google.com/cloudagents/install-logging-agent.sh
bash install-logging-agent.sh

docker network create esnet

## Elasticsearch 
# TODO make sure that when the process gets restarted with different memory and CPU requirements, this command update. Perhaps needs to be in a systemd service?
docker run -d -p 9200:9200 -p 9300:9300 \
    --name elasticsearch \
    --network=esnet \
    -v esdatavol:/usr/share/elasticsearch/data \
    -e "discovery.type=single-node" \
    -e "xpack.security.enabled=false" \
    -e "cluster.name=hannibal" \
    -e "bootstrap.memory_lock=true" \
    -e "ES_JAVA_OPTS=-Xms${ES_HEAP}m -Xmx${ES_HEAP}m" \
    -e "reindex.remote.whitelist=10.*.*.*:*, _local_:*" \
    --log-driver=gcplogs \
    --log-opt gcp-log-cmd=true \
    --cpus=${ES_CPU} \
    -m ${ES_MEM}M \
    --ulimit memlock=-1:-1 \
    --restart=always \
    quay.io/opentargets/docker-elasticsearch-singlenode:5.6
    #docker.elastic.co/elasticsearch/elasticsearch:5.6.2

# # NOTE: we don't have to explicity set the ulimits over files, since
# the debian docker daemon sets acceptable ones 
# Tested with `docker run --rm centos:7 /bin/bash -c 'ulimit -Hn && ulimit -Sn && ulimit -Hu && ulimit -Su'`



## Change index settings (after ES is ready)
# # wait enough to get elasticsearch running and ready
until $(curl --output /dev/null --silent --head --fail http://127.0.0.1:9200); do
    printf '.'
    sleep 1
done

echo '{"index" : {"number_of_replicas" : 0}}' | http PUT :9200/_settings

echo '{
    "template": ".monitoring-*",
    "order": 1,
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0
        }
}' | http PUT :9200/_template/custom_monitoring

echo '{
    "template": ".triggered*",
    "order": 1,
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0
        }
}' | http PUT :9200/_template/custom_monitoring

echo '{
    "template": ".watches*",
    "order": 1,
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0
        }
}' | http PUT :9200/_template/custom_monitoring


echo configure gcs snapshot plugin repository
cat <<EOF > /root/snapshot_gcs.json
{
  "type": "gcs",
  "settings": {
    "bucket": "ot-snapshots",
    "base_path": "${INSTANCE_NAME}",
    "max_restore_bytes_per_sec": "1000mb",
    "max_snapshot_bytes_per_sec": "1000mb"
  }
}
EOF

http --check-status -p b --pretty none PUT :9200/_snapshot/${INSTANCE_NAME} @/root/snapshot_gcs.json



## tmux niceties
wget -O ~/.tmux.conf https://git.io/v9FuI

## python 
pip install --upgrade pip
pip install elasticsearch-curator

mkdir /hannibal
mkdir /hannibal/logs
mkdir /hannibal/data

## clone the hannibal repo with the task definition and install python packages needed
git clone https://github.com/opentargets/hannibal.git /hannibal/src
pip install -r /hannibal/src/requirements.txt

mkdir /etc/luigi
cat <<EOF > /etc/luigi/luigi.cfg
# scheduler options first

[core]
logging_conf_file=hannibal_logging.cfg

[retcode]
# The following return codes are the recommended exit codes for Luigi
# They are in increasing level of severity (for most applications)
already_running=10
missing_data=20
not_run=25
task_failed=30
scheduling_error=35
unhandled_exception=40


# From here onwards, the config file will contain URLs for each of the steps
# and will keep track of each version using version control

# We will branch the data_pipeline for each release (eg. mar_2017)
# and use that branch in the config.

# Specifying parameter values here in the config file has the added benefit
# that it becomes possible to specify the parameters only on the classes
# that actually use the parameters. This avoids long command-line calls
# such as: 
# luigi --module opentargETL GeneData --date 2017-03-15 --OpenTargETLTask-date 2017-03-15
# where you need to specify the parameter for each task in the dependency graph

# an alternative approach is to use @inherits and @requires defined in luigi.util
# http://luigi.readthedocs.io/en/stable/api/luigi.util.html

[elasticsearch]
marker-index = hannibal_status_log
marker-doc-type = entry
eshost = elasticsearch
esport = 9200

[DEFAULT] 

# the branch info is inherited by all tasks, but they !!MUST!! have a a section
# below:

mrtargetbranch = ${CONTAINER_TAG}
mrtargetrepo = eu.gcr.io/open-targets/mrtarget
#data_version = hannibal-17.09
[UniProt]
[Ensembl]
[Expression]
[Reactome]
[GeneData]
[EFO]
[ECO]
[Validate]
[EvidenceObjects]
[InjectedEvidence]
[AssociationObjects]
[SearchObjects]
[Relations]
[DataRelease]
[DataDump]

[evidences]
# gsutil ls gs://ot-releases/17.09 | sed 's/gs/http/' | sed 's/\/\//\/\/storage.googleapis.com\//' | sed 's/^.*$/"&",/g'
t2d_evidence_sources = [
    "http://storage.googleapis.com/ot-releases/17.09/atlas-08-09-2017.json.gz",
    "http://storage.googleapis.com/ot-releases/17.09/cancer_gene_census-30-08-2017.json.gz",
    "http://storage.googleapis.com/ot-releases/17.09/chembl-10-10-2017.json.gz",
    "http://storage.googleapis.com/ot-releases/17.09/europepmc-24-08-2017.json.gz",
    "http://storage.googleapis.com/ot-releases/17.09/eva-24-08-2017.json.gz",
    "http://storage.googleapis.com/ot-releases/17.09/gene2phenotype-30-08-2017.json.gz",
    "http://storage.googleapis.com/ot-releases/17.09/genomics_england-05-09-2017.json",
    "http://storage.googleapis.com/ot-releases/17.09/gwas_catalog-29-08-2017.json.gz",
    "http://storage.googleapis.com/ot-releases/17.09/intogen-30-08-2017.json.gz",
    "http://storage.googleapis.com/ot-releases/17.09/phenodigm-01-09-2017.json.gz",
    "http://storage.googleapis.com/ot-releases/17.09/phewas_catalog-11-09-2017.json.gz",
    "http://storage.googleapis.com/ot-releases/17.09/phewas_catalog_12-10-2017.json.gz",
    "http://storage.googleapis.com/ot-releases/17.09/reactome-07-08-2017.json.gz",
    "http://storage.googleapis.com/ot-releases/17.09/slapenrich-22-09-2017.json.gz",
    "http://storage.googleapis.com/ot-releases/17.09/uniprot-07-09-2017.json.gz"
    ]




EOF

gcloud docker -- pull eu.gcr.io/open-targets/mrtarget:${CONTAINER_TAG}

## central scheduler for the visualization
luigid --background

echo >> start luigi run
cd /hannibal/src
export LUIGI_CONFIG_PATH=~/luigi.cfg
PYTHONPATH="." luigi --module pipeline-dockertask DataRelease --workers 1

# tmux new -d -s luigi
# tmux send-keys -t luigi 'source venv/bin/activate' C-m
# tmux send-keys -t luigi 'export LUIGI_CONFIG_PATH=/hannibal/luigi.cfg' C-m 
# tmux send-keys -t luigi 'PYTHONPATH="." luigi --module pipeline-dockertask DataRelease --local-scheduler --workers 3' C-m







# TODO:
# * make sure it runs 
# * es as service ?rc.d 
# * luigi scheduler as a service/cron?
